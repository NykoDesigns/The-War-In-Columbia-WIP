// BatchDecompile.java — Ghidra headless script
// Decompiles a list of functions and traces their call trees to depth N.
// Usage: analyzeHeadless ... -postScript BatchDecompile.java <depth> <outfile> <addr1> [addr2] ...
// Output: JSON with {functions: [{addr, name, code, calls: [addr...], calledBy: [addr...]}]}

import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.pcode.*;
import ghidra.program.model.symbol.*;

import java.io.*;
import java.util.*;

public class BatchDecompile extends GhidraScript {

    private DecompInterface decomp;
    private Map<String, Map<String, Object>> results = new LinkedHashMap<>();
    private int maxDepth;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 3) {
            println("Usage: BatchDecompile <depth> <outfile> <addr1> [addr2] ...");
            return;
        }
        maxDepth = Integer.parseInt(args[0]);
        String outFile = args[1];

        decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        DecompileOptions opts = new DecompileOptions();
        decomp.setOptions(opts);

        // Seed addresses
        Set<String> toProcess = new LinkedHashSet<>();
        for (int i = 2; i < args.length; i++) {
            toProcess.add(args[i].toLowerCase().replace("0x", ""));
        }

        // BFS to depth N
        Set<String> processed = new HashSet<>();
        int depth = 0;
        while (!toProcess.isEmpty() && depth <= maxDepth) {
            Set<String> nextLevel = new LinkedHashSet<>();
            for (String addrStr : toProcess) {
                if (processed.contains(addrStr)) continue;
                processed.add(addrStr);

                Address addr = currentProgram.getAddressFactory()
                    .getDefaultAddressSpace().getAddress(Long.parseLong(addrStr, 16));
                Function func = getFunctionAt(addr);
                if (func == null) {
                    func = getFunctionContaining(addr);
                }
                if (func == null) continue;

                String funcAddr = func.getEntryPoint().toString().toLowerCase();
                if (results.containsKey(funcAddr)) continue;

                // Decompile
                DecompileResults res = decomp.decompileFunction(func, 30, monitor);
                String code = "";
                if (res != null && res.decompileCompleted()) {
                    code = res.getDecompiledFunction().getC();
                }

                // Find called functions
                List<String> calls = new ArrayList<>();
                Set<Function> calledFuncs = func.getCalledFunctions(monitor);
                for (Function cf : calledFuncs) {
                    String cAddr = cf.getEntryPoint().toString().toLowerCase();
                    calls.add(cAddr);
                    if (depth < maxDepth && !processed.contains(cAddr)) {
                        nextLevel.add(cAddr);
                    }
                }

                // Find callers
                List<String> callers = new ArrayList<>();
                Set<Function> callingFuncs = func.getCallingFunctions(monitor);
                for (Function cf : callingFuncs) {
                    callers.add(cf.getEntryPoint().toString().toLowerCase());
                }

                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("addr", funcAddr);
                entry.put("name", func.getName());
                entry.put("signature", func.getSignature().getPrototypeString());
                entry.put("size", func.getBody().getNumAddresses());
                entry.put("calls", calls);
                entry.put("calledBy", callers);
                entry.put("code", code);
                entry.put("depth", depth);
                results.put(funcAddr, entry);
            }
            toProcess = nextLevel;
            depth++;
        }

        decomp.dispose();

        // Write JSON
        StringBuilder sb = new StringBuilder();
        sb.append("{\"functions\":[\n");
        boolean first = true;
        for (Map<String, Object> e : results.values()) {
            if (!first) sb.append(",\n");
            first = false;
            sb.append("  {\"addr\":\"").append(e.get("addr")).append("\",");
            sb.append("\"name\":\"").append(e.get("name")).append("\",");
            sb.append("\"signature\":\"").append(escJson((String)e.get("signature"))).append("\",");
            sb.append("\"size\":").append(e.get("size")).append(",");
            sb.append("\"depth\":").append(e.get("depth")).append(",");
            sb.append("\"calls\":").append(listToJson((List<String>)e.get("calls"))).append(",");
            sb.append("\"calledBy\":").append(listToJson((List<String>)e.get("calledBy"))).append(",");
            sb.append("\"code\":\"").append(escJson((String)e.get("code"))).append("\"}");
        }
        sb.append("\n],\"count\":").append(results.size()).append("}\n");

        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.write(sb.toString());
        pw.close();
        println("[BatchDecompile] wrote " + outFile + " (" + results.size() + " functions)");
    }

    private String escJson(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }

    private String listToJson(List<String> list) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < list.size(); i++) {
            if (i > 0) sb.append(",");
            sb.append("\"").append(list.get(i)).append("\"");
        }
        sb.append("]");
        return sb.toString();
    }
}

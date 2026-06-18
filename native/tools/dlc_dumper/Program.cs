using System;
using System.IO;
using System.Linq;
using System.Text;
using UELib;
using UELib.Core;

namespace DlcDumper
{
    class Program
    {
        static void Main(string[] args)
        {
            string pkgPath = args.Length > 0 ? args[0] :
                @"Z:\UEdecompress\unpacked\dlcb_CoalescedItems.xxx";
            string outputDir = args.Length > 1 ? args[1] :
                @"Z:\TheWarInColumbia\native\tools\dlc_dump";

            Directory.CreateDirectory(outputDir);

            Console.WriteLine($"Loading: {pkgPath}");
            var pkg = UnrealLoader.LoadFullPackage(pkgPath, FileAccess.Read);
            pkg.InitializePackage(UnrealPackage.InitFlags.All);
            Console.WriteLine($"Loaded: {pkg.Exports?.Count ?? 0} exports, {pkg.Names?.Count ?? 0} names");

            // Target classes for DLC vigor integration
            string[] targetClasses = {
                "XWeaponWinterbolt", "XWeaponChameleon", "XWeaponReturnToSender",
                "XDLCBDamageType", "XDamageType", "XActorSpawningProjectile",
                "XWeapon", "XWeaponCharge", "XWeaponMurderOfCrows",
                "XWeaponRollingThunder", "XWeaponUndertow"
            };

            // Target object names (specific DLC objects)
            string[] targetNames = {
                "Plasmid_WinterBolt", "Plasmid_Chameleon",
                "Plasmid_ReturnToSenderBase", "Plasmid_ReturnToSenderInsta",
                "Plasmid_WinterBolt_TapDamage", "BeamCannonDLCBDamage",
                "Plasmid_WinterBolt_TapProjectile",
                "WinterBolt_HoldGrenade_Damage",
                // Base game vigors for comparison
                "Plasmid_DevilsKiss", "Plasmid_BuckingBroncoBase",
                "Plasmid_VoltSwarmFounder", "Plasmid_MurderOfCrowsBase",
                "Plasmid_UndertowBase", "Plasmid_Charge"
            };

            if (pkg.Exports == null) { Console.WriteLine("No exports!"); return; }

            foreach (var exp in pkg.Exports)
            {
                if (exp == null) continue;

                string className = exp.ClassName ?? "";
                string objName = exp.ObjectName ?? "";

                // Check if this is an object we care about
                bool isTarget = targetNames.Any(t => objName.Equals(t, StringComparison.OrdinalIgnoreCase));
                if (!isTarget) continue;

                string outFile = Path.Combine(outputDir, $"{className}_{objName}.txt");
                var sb = new StringBuilder();
                sb.AppendLine($"// ============================================");
                sb.AppendLine($"// Class: {className}");
                sb.AppendLine($"// Object: {objName}");
                sb.AppendLine($"// Outer: {exp.OuterName}");
                sb.AppendLine($"// SerialSize: {exp.SerialSize}");
                sb.AppendLine($"// SerialOffset: 0x{exp.SerialOffset:X}");
                sb.AppendLine($"// ============================================");
                sb.AppendLine();

                try
                {
                    var obj = exp.Object;
                    if (obj != null)
                    {
                        // Try to get decompiled/content view
                        try
                        {
                            string decompiled = obj.Decompile();
                            if (!string.IsNullOrWhiteSpace(decompiled))
                            {
                                sb.AppendLine("// === Decompiled ===");
                                sb.AppendLine(decompiled);
                                sb.AppendLine();
                            }
                        }
                        catch (Exception ex)
                        {
                            sb.AppendLine($"// Decompile failed: {ex.Message}");
                        }

                        // Dump properties if available
                        if (obj is UObject uobj)
                        {
                            try
                            {
                                var props = uobj.Properties;
                                if (props != null && props.Count > 0)
                                {
                                    sb.AppendLine("// === Properties ===");
                                    foreach (var prop in props)
                                    {
                                        sb.AppendLine($"  {prop}");
                                    }
                                    sb.AppendLine();
                                }
                            }
                            catch { }
                        }
                    }
                }
                catch (Exception ex)
                {
                    sb.AppendLine($"// Object load failed: {ex.Message}");
                }

                File.WriteAllText(outFile, sb.ToString());
                Console.WriteLine($"  [{className}] {objName} -> {Path.GetFileName(outFile)}");
            }

            // Also dump all DLC-specific damage types
            string dmgFile = Path.Combine(outputDir, "_DLC_DamageTypes.txt");
            var dmgSb = new StringBuilder();
            dmgSb.AppendLine("// All DLC-specific DamageTypes");
            foreach (var exp in pkg.Exports)
            {
                if (exp == null) continue;
                string cn = exp.ClassName ?? "";
                string on = exp.ObjectName ?? "";
                if (cn == "XDLCBDamageType" || (cn == "XDamageType" && on.Contains("DLCB")))
                {
                    dmgSb.AppendLine($"  {cn} | {on} | sz={exp.SerialSize}");
                }
                if (cn == "XDamageType" && on.Contains("WinterBolt"))
                {
                    dmgSb.AppendLine($"  {cn} | {on} | sz={exp.SerialSize}");
                }
            }
            File.WriteAllText(dmgFile, dmgSb.ToString());

            Console.WriteLine($"\nOutput: {outputDir}");
            Console.WriteLine("Done.");
        }
    }
}

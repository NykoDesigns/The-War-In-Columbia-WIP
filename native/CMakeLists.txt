cmake_minimum_required(VERSION 3.20)
project(WICMemMon VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Static runtime — no VC++ redist needed
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# Must be 32-bit (BioShock Infinite is x86)
if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "Must build as 32-bit (x86). Use: cmake -A Win32")
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# Game directory for deployment
set(BIOINF_GAME_DIR "D:/SteamLibrary/steamapps/common/BioShock Infinite/Binaries/Win32"
    CACHE PATH "BioShock Infinite Win32 binaries directory")

# ─── MinHook (fetched automatically) ─────────────────────────────────
include(FetchContent)
FetchContent_Declare(
    minhook
    GIT_REPOSITORY https://github.com/TsudaKageyu/minhook.git
    GIT_TAG        master
    GIT_SHALLOW    TRUE
)
FetchContent_MakeAvailable(minhook)

# ─── Options ─────────────────────────────────────────────────────────
# Toggle the VirtualAlloc memory monitor. Disable to validate the proxy
# forwarder mechanism in isolation.
option(WIC_ENABLE_MONITOR "Enable the VirtualAlloc memory monitor" ON)

# ─── winmm.dll proxy (the memory monitor lives inside) ───────────────
set(PROXY_SOURCES
    src/winmm_proxy.cpp
    src/winmm_forwards.h
)
if(WIC_ENABLE_MONITOR)
    list(APPEND PROXY_SOURCES
        src/mem_monitor.cpp src/mem_monitor.h
        src/ue3_spawn.cpp src/ue3_spawn.h)
endif()

add_library(winmm_proxy SHARED ${PROXY_SOURCES})

set_target_properties(winmm_proxy PROPERTIES
    OUTPUT_NAME "winmm"
    PREFIX ""
    SUFFIX ".dll"
)

target_compile_definitions(winmm_proxy PRIVATE
    NOMINMAX
    WIN32_LEAN_AND_MEAN
)

if(WIC_ENABLE_MONITOR)
    target_link_libraries(winmm_proxy PRIVATE minhook)
    target_compile_definitions(winmm_proxy PRIVATE WIC_ENABLE_MONITOR)
endif()

if(MSVC)
    target_link_options(winmm_proxy PRIVATE /SAFESEH:NO)
endif()

# Auto-deploy after build
if(BIOINF_GAME_DIR)
    add_custom_command(TARGET winmm_proxy POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "$<TARGET_FILE:winmm_proxy>"
            "${BIOINF_GAME_DIR}/winmm.dll"
        COMMENT "Deploying winmm.dll -> ${BIOINF_GAME_DIR}"
    )
endif()

# Note: winmm_orig.dll (a copy of the real 32-bit winmm.dll from SysWOW64)
# must be present in the game directory for the forwarders to resolve.
# It is deployed separately by the deploy script, not by CMake, because it
# is a system file copy rather than a build artifact.

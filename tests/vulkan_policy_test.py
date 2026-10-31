#!/usr/bin/env python3
"""Prove launch policy reaches native children without JVM calls or Vulkan loading."""
import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--jdk-home", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    args = parser.parse_args()
    boot = (args.source / "runtime/java/com/macapk/loader/Boot.java").read_text()
    start = boot.index("private static void noteGuestVulkan(")
    end = boot.index("private static volatile String sApkPath", start)
    policy = boot[start:end]
    assert "NativeOs.publishGuestVulkanPolicy(on)" in policy, "Resolved policy never reaches host environment"
    assert policy.index("System.setProperty") < policy.index("NativeOs.publishGuestVulkanPolicy(on)"), "Publish unresolved policy"
    assert boot.index("noteGuestVulkan(manifest);") < boot.index("appCl = new AppClassLoader"), "Policy published after guest class loading"
    shim = (args.source / "runtime/translator/src/bionic_shim_vulkan.cpp").read_text()
    begin = shim.index("bool guest_vulkan_enabled() {")
    finish = shim.index("\n}\n", begin) + 3
    args.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vulkan-policy-", dir=args.work_root) as temporary:
        root = Path(temporary)
        native = args.source / "runtime/src/native_os.cpp"
        code = '#include "' + str(native) + '"\n'
        code += '#include <sys/wait.h>\n#include <cstring>\n#include <cassert>\n'
        code += 'bool app_requires_vulkan(){_exit(97);}\n' + shim[begin:finish]
        code += r'''
int main(int argc,char**argv){
 bool expected=argc>1&&argv[1][0]=='1';
 setenv("MACAPK_GUEST_VULKAN","auto",1);
 assert(macapk::osnative::NativeOs_publishGuestVulkanPolicy(nullptr,nullptr,expected)==0);
 assert(strcmp(getenv("MACAPK_GUEST_VULKAN"),expected?"1":"0")==0);
 pid_t child=fork();assert(child>=0);
 if(child==0)_exit(guest_vulkan_enabled()==expected?0:98);
 int status=0;assert(waitpid(child,&status,0)==child);
 assert(WIFEXITED(status)&&WEXITSTATUS(status)==0);
 assert(guest_vulkan_enabled()==expected);
 puts("PASS parent publication and child native-only Vulkan policy");
}
'''
        source = root / "policy.cpp"
        source.write_text(code)
        binary = root / "policy"
        subprocess.run(["clang++", "-std=c++17", "-I" + str(args.jdk_home / "include"),
                        "-I" + str(args.jdk_home / "include/darwin"), str(source),
                        "-lcompression", "-o", str(binary)], check=True, timeout=30)
        for mode in ("0", "1"):
            subprocess.run([str(binary), mode], check=True, timeout=5)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check Mach available RAM, Android low-memory decisions, and the proc mirror."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

JAVA = r'''package fixture;
import android.app.ActivityManager;import com.macapk.loader.NativeOs;
public class MemoryContract {
 static native void force(long value);static native long sample();
 static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 public static void main(String[] args)throws Exception{
  System.load(args[0]);long actual=sample();check(actual>=0,"Mach snapshot failed");
  ActivityManager manager=new ActivityManager();ActivityManager.MemoryInfo info=new ActivityManager.MemoryInfo();
  force(0);manager.getMemoryInfo(info);check(info.availMem==0&&info.lowMemory,"genuine low RAM hidden");
  force(4L<<30);manager.getMemoryInfo(info);check(info.availMem==Math.min(4L<<30,info.totalMem),"inactive RAM missing");check(!info.lowMemory,"reclaimable RAM falsely low");
  force(Long.MAX_VALUE);manager.getMemoryInfo(info);check(info.availMem==info.totalMem,"available RAM exceeds physical RAM");
  force(-1);manager.getMemoryInfo(info);check(info.availMem>0&&info.availMem<=info.totalMem,"MXBean fallback failed");
  force(4L<<30);var method=com.macapk.loader.Boot.class.getDeclaredMethod("writeJavaProcMirror",String.class);method.setAccessible(true);method.invoke(null,args[1]);
  String mirror=java.nio.file.Files.readString(java.nio.file.Path.of(args[1],"proc/meminfo"));
  long available=-1,free=-1;for(String line:mirror.split("\n")){String[] parts=line.trim().split("\\s+");if(parts[0].equals("MemAvailable:"))available=Long.parseLong(parts[1])*1024;if(parts[0].equals("MemFree:"))free=Long.parseLong(parts[1])*1024;}
  manager.getMemoryInfo(info);check(available==info.availMem,"proc and Android available RAM disagree");check(free>=0&&free<=info.totalMem,"free RAM invalid");
  if(args.length>2){
   android.content.Context context=new android.content.ContextWrapper(null){public Object getSystemService(String name){return name.equals("activity")?manager:null;}};
   var gate=Class.forName("X.209").getMethod("A00",android.content.Context.class);
   force(78643200L-1);check((Boolean)gate.invoke(null,context),"real camera gate ignored low memory");
   force(78643200L);check(!(Boolean)gate.invoke(null,context),"real camera threshold boundary wrong");
   force(32L<<20);check((Boolean)gate.invoke(null,context),"real camera gate hid genuine low RAM");
   force((32L+2048L)<<20);check(!(Boolean)gate.invoke(null,context),"real camera gate rejected reclaimable RAM");
  }
  System.out.println("PASS actual Mach snapshot, low/reclaimable/fallback/clamp, and proc availability consistency");
 }
}'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--jdk-home", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--source-overlay", action="store_true")
    parser.add_argument("--app-classes", type=Path)
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="available-memory-", dir=args.work_root) as temporary:
        root = Path(temporary)
        native = root / "memory.cpp"
        native.write_text('#include "' + str(args.source / 'runtime/src/native_os.cpp') + '"\n' + r'''
#include <cassert>
static jlong forced=-1;
static jlong fixed(JNIEnv*,jclass){return forced;}
extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM*vm,void*){
 JNIEnv*env=nullptr;if(vm->GetEnv((void**)&env,JNI_VERSION_1_6)!=JNI_OK)return JNI_ERR;
 using namespace macapk::osnative;
 assert(available_memory_bytes(10,20,16384)==491520);
 assert(available_memory_bytes(2048,131072,16384)==((32LL+2048LL)<<20));
 assert(available_memory_bytes(0,0,16384)==0);
 assert(available_memory_bytes(1,1,0)==-1);
 assert(available_memory_bytes(UINT64_MAX,1,16384)==INT64_MAX);
 RegisterNativeOsMethods(env);return JNI_VERSION_1_6;
}
extern "C" JNIEXPORT jlong JNICALL Java_fixture_MemoryContract_sample(JNIEnv*,jclass){return macapk::osnative::NativeOs_availableMemoryBytes(nullptr,nullptr);}
extern "C" JNIEXPORT void JNICALL Java_fixture_MemoryContract_force(JNIEnv*env,jclass,jlong value){
 forced=value;jclass cls=env->FindClass("com/macapk/loader/NativeOs");
 JNINativeMethod method{(char*)"availableMemoryBytes",(char*)"()J",(void*)fixed};assert(env->RegisterNatives(cls,&method,1)==0);
}
''')
        library = root / "memory.dylib"
        subprocess.run(["clang++", "-std=c++17", "-shared", "-fPIC", "-I" + str(args.jdk_home / "include"),
                        "-I" + str(args.jdk_home / "include/darwin"), str(native), "-lcompression", "-o", str(library)], check=True, timeout=30)
        java = root / "fixture/MemoryContract.java"
        java.parent.mkdir()
        java.write_text(JAVA)
        # Isolate the proc alias so this test cannot change a running app's mirror.
        boot = root / "com/macapk/loader/Boot.java"
        boot.parent.mkdir(parents=True)
        boot.write_text((args.source / "runtime/java/com/macapk/loader/Boot.java").read_text().replace('"/tmp/mcmeminf"', '"' + str(root / "proc-alias") + '"'))
        cp = os.pathsep.join(str(args.source / "runtime/build/lib" / name) for name in ("android-framework.jar", "macapk-loader.jar"))
        if args.app_classes:
            cp += os.pathsep + str(args.app_classes)
        files = [str(java), str(boot)]
        if args.source_overlay:
            files += [str(args.source / "runtime/java" / name) for name in ("android/app/ActivityManager.java", "com/macapk/loader/NativeOs.java")]
        subprocess.run([str(args.jdk_home / "bin/javac"), "-cp", cp, "-d", str(root), *files], check=True, timeout=60)
        command = [str(args.jdk_home / "bin/java"), "-cp", str(root) + os.pathsep + cp, "fixture.MemoryContract", str(library), str(root / "android")]
        if args.app_classes:
            command.append("actual-camera-gate")
        subprocess.run(command, check=True, timeout=15, env=dict(os.environ, MACAPK_LOG_LEVEL="99"))


if __name__ == "__main__":
    main()

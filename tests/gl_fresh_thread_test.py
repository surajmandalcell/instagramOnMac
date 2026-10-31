#!/usr/bin/env python3
"""Exercise the production GL error bridge on fresh threads and real ANGLE contexts."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

CPP = r'''
#include <jni.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <EGL/eglext_angle.h>
#include <GLES2/gl2.h>
#include <thread>
#include <cstdio>
BRIDGE
int main(){
 int failed=0;
 std::thread fresh([&]{
  if(GLES20_glGetError(nullptr,nullptr)!=GL_NO_ERROR)failed=1;
  eglReleaseThread();
  if(GLES20_glGetError(nullptr,nullptr)!=GL_NO_ERROR)failed=2;
 });fresh.join();if(failed)return failed;
 auto platform=(PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
 EGLint attributes[]={EGL_PLATFORM_ANGLE_TYPE_ANGLE,EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE,EGL_NONE};
 EGLDisplay display=platform(EGL_PLATFORM_ANGLE_ANGLE,nullptr,attributes);
 if(!eglInitialize(display,nullptr,nullptr))return 3;
 EGLint configAttributes[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_NONE};
 EGLConfig config;EGLint count=0;if(!eglChooseConfig(display,configAttributes,&config,1,&count)||count!=1)return 4;
 EGLint size[]={EGL_WIDTH,4,EGL_HEIGHT,4,EGL_NONE};EGLSurface surface=eglCreatePbufferSurface(display,config,size);
 EGLint version[]={EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE};EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,version);
 if(!eglMakeCurrent(display,surface,surface,context))return 5;
 glBindTexture(0xdead,0);
 if(GLES20_glGetError(nullptr,nullptr)!=GL_INVALID_ENUM)return 6;
 if(GLES20_glGetError(nullptr,nullptr)!=GL_NO_ERROR)return 7;
 if(eglGetCurrentContext()!=context)return 8;
 eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
 eglDestroyContext(display,context);eglDestroySurface(display,surface);eglTerminate(display);eglReleaseThread();
 std::puts("PASS fresh thread and released TLS; real GL error preserved and consumed once; current context unchanged");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "jdk-home", "work-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--bridge-source", type=Path)
    parser.add_argument("--expect-crash", action="store_true")
    args = parser.parse_args()
    source = args.bridge_source or args.source / "runtime/src/native_methods.cpp"
    match = re.search(r"jint GLES20_glGetError\(JNIEnv\*[^}]+\}", source.read_text())
    if not match:
        raise AssertionError("Production GL error bridge was not found")
    args.work_root.mkdir(parents=True, exist_ok=True)
    angle = (args.source / "thirdparty/angle-prebuilt").resolve()
    with tempfile.TemporaryDirectory(prefix="gl-tls-", dir=args.work_root) as directory:
        work = Path(directory)
        (work / "test.cpp").write_text(CPP.replace("BRIDGE", match.group()))
        subprocess.run(["clang++", "-std=c++17", "-DMACAPK_HAS_ANGLE", "-I" + str(args.jdk_home / "include"),
                        "-I" + str(args.jdk_home / "include/darwin"), "-I" + str(angle / "include"),
                        str(work / "test.cpp"), "-L" + str(angle / "lib"), "-lEGL", "-lGLESv2",
                        "-Wl,-rpath," + str(angle / "lib"), "-o", str(work / "test")], check=True, timeout=30)
        result = subprocess.run([str(work / "test")], cwd=angle / "lib", timeout=20,
                                env=dict(os.environ), capture_output=True, text=True)
        if args.expect_crash:
            if result.returncode != -11:
                raise AssertionError("Baseline did not reproduce SIGSEGV: " + str(result.returncode))
            print("PASS baseline reproduces fresh-thread SIGSEGV")
        else:
            if result.returncode:
                raise AssertionError("GL error contract failed: " + str(result.returncode))
            print(result.stdout.strip())


if __name__ == "__main__":
    main()

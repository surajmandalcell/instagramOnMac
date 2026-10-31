#!/usr/bin/env python3
"""Real ANGLE pixels through the production surface reader and AVC encoder."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

CPP = r'''
#include <jni.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <EGL/eglext_angle.h>
#include <GLES2/gl2.h>
namespace macapk::video_encoder{void RegisterNativeVideoEncoderMethods(JNIEnv*);}
static EGLDisplay display;static EGLSurface surface;static EGLContext context;
static void integers(JNIEnv*e,jclass,jint key,jintArray result,jint offset){GLint value=0;glGetIntegerv(key,&value);e->SetIntArrayRegion(result,offset,1,&value);}
static void readPixels(JNIEnv*e,jclass,jint x,jint y,jint w,jint h,jint format,jint type,jobject pixels){glReadPixels(x,y,w,h,format,type,e->GetDirectBufferAddress(pixels));}
static void pixelStore(JNIEnv*,jclass,jint key,jint value){glPixelStorei(key,value);}
static void bindFramebuffer(JNIEnv*,jclass,jint target,jint value){glBindFramebuffer(target,value);}
extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM*vm,void*){
 JNIEnv*e=nullptr;if(vm->GetEnv((void**)&e,JNI_VERSION_21)!=JNI_OK)return JNI_ERR;
 macapk::video_encoder::RegisterNativeVideoEncoderMethods(e);
 JNINativeMethod methods[]={
 {(char*)"glGetIntegerv",(char*)"(I[II)V",(void*)integers},
 {(char*)"glReadPixels",(char*)"(IIIIIILjava/nio/Buffer;)V",(void*)readPixels},
 {(char*)"glPixelStorei",(char*)"(II)V",(void*)pixelStore},
 {(char*)"glBindFramebuffer",(char*)"(II)V",(void*)bindFramebuffer}};
 jclass c=e->FindClass("android/opengl/GLES20");if(e->RegisterNatives(c,methods,4)!=0)return JNI_ERR;return JNI_VERSION_21;
}
extern "C" JNIEXPORT void JNICALL Java_fixture_EncoderContract_initialize(JNIEnv*e,jclass){
 auto platform=(PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
 EGLint attrs[]={EGL_PLATFORM_ANGLE_TYPE_ANGLE,EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE,EGL_NONE};display=platform(EGL_PLATFORM_ANGLE_ANGLE,nullptr,attrs);
 if(!eglInitialize(display,nullptr,nullptr)){e->ThrowNew(e->FindClass("java/lang/AssertionError"),"EGL initialize failed");return;}
 EGLint configAttrs[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE};EGLConfig config;EGLint count=0;eglChooseConfig(display,configAttrs,&config,1,&count);
 EGLint surfaceAttrs[]={EGL_WIDTH,64,EGL_HEIGHT,48,EGL_NONE};surface=eglCreatePbufferSurface(display,config,surfaceAttrs);
 EGLint contextAttrs[]={EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE};context=eglCreateContext(display,config,EGL_NO_CONTEXT,contextAttrs);
 if(!eglMakeCurrent(display,surface,surface,context))e->ThrowNew(e->FindClass("java/lang/AssertionError"),"EGL make current failed");
}
extern "C" JNIEXPORT void JNICALL Java_fixture_EncoderContract_color(JNIEnv*,jclass,jboolean red){glClearColor(red?1:0,0,red?0:1,1);glClear(GL_COLOR_BUFFER_BIT);glFinish();}
extern "C" JNIEXPORT jlongArray JNICALL Java_fixture_EncoderContract_handles(JNIEnv*e,jclass){jlong values[]={(jlong)(uintptr_t)display,(jlong)(uintptr_t)surface};jlongArray result=e->NewLongArray(2);e->SetLongArrayRegion(result,0,2,values);return result;}
extern "C" JNIEXPORT void JNICALL Java_fixture_EncoderContract_finish(JNIEnv*,jclass){eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);eglDestroyContext(display,context);eglDestroySurface(display,surface);eglTerminate(display);}
'''

JAVA = r'''package fixture;
import android.media.*;import android.view.Surface;import java.nio.*;import java.nio.file.*;import java.util.*;
public class EncoderContract{
 static native void initialize();static native void color(boolean red);static native void finish();static native long[] handles();
 static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 static void drain(MediaCodec encoder,java.io.OutputStream stream,List<Long> pts,boolean[] eos)throws Exception{
  MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();for(;;){int index=encoder.dequeueOutputBuffer(info,0);
   if(index==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED){MediaFormat format=encoder.getOutputFormat();check(format.getByteBuffer("csd-0").remaining()>4&&format.getByteBuffer("csd-1").remaining()>4,"SPS/PPS missing");for(String key:List.of("csd-0","csd-1")){ByteBuffer data=format.getByteBuffer(key).duplicate();byte[] bytes=new byte[data.remaining()];data.get(bytes);stream.write(bytes);}continue;}
   if(index<0)return;ByteBuffer data=encoder.getOutputBuffer(index);check(data!=null&&data.isDirect(),"encoder returned no direct compressed buffer");byte[] bytes=new byte[info.size];data.get(bytes);stream.write(bytes);
   if(info.size>0)pts.add(info.presentationTimeUs);if((info.flags&4)!=0)eos[0]=true;encoder.releaseOutputBuffer(index,false);
  }
 }
 public static void main(String[]args)throws Exception{
  System.load(args[0]);initialize();MediaCodec encoder=MediaCodec.createEncoderByType("video/avc");
  MediaFormat format=MediaFormat.createVideoFormat("video/avc",64,48);format.setInteger("color-format",MediaFormat.COLOR_FormatSurface);format.setInteger("bitrate",200000);format.setInteger("frame-rate",10);format.setFloat("i-frame-interval",1f);encoder.configure(format,null,null,MediaCodec.CONFIGURE_FLAG_ENCODE);
  Surface input=encoder.createInputSurface();android.graphics.SurfaceTexture texture=input.macapkGetSurfaceTexture();
  Class<?> windowClass=Class.forName("javax.microedition.khronos.egl.MacApkGlWindow");var constructor=windowClass.getDeclaredConstructors()[0];constructor.setAccessible(true);Object window=constructor.newInstance(null,null,texture);
  for(String name:List.of("mW","mH")){var field=windowClass.getDeclaredField(name);field.setAccessible(true);field.setInt(window,name.equals("mW")?64:48);}
  long[] handles=handles();Class<?> keyClass=Class.forName("javax.microedition.khronos.egl.MacApkGlWindow$Egl14Key");var keyConstructor=keyClass.getDeclaredConstructors()[0];keyConstructor.setAccessible(true);Object key=keyConstructor.newInstance(handles[0],handles[1]);var registryField=windowClass.getDeclaredField("EGL14_WINDOWS");registryField.setAccessible(true);var registry=(java.util.Map<Object,Object>)registryField.get(null);registry.put(key,window);
  var queue=windowClass.getDeclaredMethod("queueFrame",int.class);queue.setAccessible(true);encoder.start();List<Long> pts=new ArrayList<>();boolean[] eos={false};
  try(var stream=Files.newOutputStream(Path.of(args[1]))){
   for(int i=0;i<12;i++){color(i%2==0);check(javax.microedition.khronos.egl.MacApkGlWindow.egl14PresentationTime(handles[0],handles[1],i*100_000_000L),"presentation time was not accepted");queue.invoke(window,2);drain(encoder,stream,pts,eos);}
   encoder.signalEndOfInputStream();long deadline=System.nanoTime()+5_000_000_000L;while(!eos[0]&&System.nanoTime()<deadline){drain(encoder,stream,pts,eos);Thread.sleep(1);}
  }finally{encoder.stop();encoder.release();registry.remove(key);finish();}
  check(eos[0]&&pts.size()==12,"real encoder frames/EOS missing: "+pts.size());for(int i=0;i<12;i++)check(pts.get(i)==i*100_000L,"presentation timestamp changed");
  check(!input.isValid(),"encoder release retained input surface");System.out.println("PASS real EGL surface to AVC packets, SPS/PPS, PTS, EOS and release");
  MediaCodec empty=MediaCodec.createEncoderByType("video/avc");empty.configure(format,null,null,MediaCodec.CONFIGURE_FLAG_ENCODE);empty.createInputSurface();empty.start();empty.signalEndOfInputStream();boolean emptyEos=false;long deadline=System.nanoTime()+2_000_000_000L;
  MediaCodec.BufferInfo emptyInfo=new MediaCodec.BufferInfo();while(!emptyEos&&System.nanoTime()<deadline){int index=empty.dequeueOutputBuffer(emptyInfo,0);if(index>=0){check(emptyInfo.size==0,"empty encoder fabricated a frame");emptyEos=(emptyInfo.flags&4)!=0;empty.releaseOutputBuffer(index,false);}}
  empty.release();check(emptyEos,"zero-input EOS stalled");
 }
}'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--jdk-home", type=Path, required=True)
    p.add_argument("--work-root", type=Path, required=True)
    p.add_argument("--source-overlay", action="store_true")
    a = p.parse_args()
    a.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="surface-encoder-", dir=a.work_root) as temporary:
        root = Path(temporary); (root / "bridge.cpp").write_text(CPP); (root / "EncoderContract.java").write_text(JAVA)
        angle = a.source / "thirdparty/angle-prebuilt"
        subprocess.run(["clang++", "-std=c++17", "-shared", "-fPIC", "-fno-objc-arc", "-I" + str(a.jdk_home / "include"), "-I" + str(a.jdk_home / "include/darwin"), "-I" + str(angle / "include"), str(root / "bridge.cpp"), str(a.source / "runtime/src/video_encoder.mm"), "-L" + str(angle / "lib"), "-lEGL", "-lGLESv2", "-Wl,-rpath," + str(angle / "lib"), "-framework", "Foundation", "-framework", "VideoToolbox", "-framework", "CoreMedia", "-framework", "CoreVideo", "-o", str(root / "backend.dylib")], check=True, timeout=60)
        cp = os.pathsep.join(str(a.source / "runtime/build/lib" / name) for name in ("android-framework.jar", "macapk-loader.jar"))
        files = [str(root / "EncoderContract.java")]
        if a.source_overlay:
            files += [str(a.source / "runtime/java" / name) for name in ("android/media/MediaCodec.java", "com/macapk/loader/NativeVideoEncoder.java", "android/view/Surface.java", "android/graphics/SurfaceTexture.java", "javax/microedition/khronos/egl/MacApkGlWindow.java")]
        subprocess.run([str(a.jdk_home / "bin/javac"), "-cp", cp, "-d", str(root), *files], check=True, timeout=30)
        subprocess.run([str(a.jdk_home / "bin/java"), "-cp", str(root) + os.pathsep + cp, "fixture.EncoderContract", str(root / "backend.dylib"), str(root / "encoded.h264")], cwd=angle / "lib", env=dict(os.environ, MACAPK_LOG_LEVEL="99"), check=True, timeout=20)
        decoded = subprocess.check_output([shutil.which("ffmpeg"), "-v", "error", "-i", str(root / "encoded.h264"), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], timeout=15)
        size = 64 * 48 * 3
        assert len(decoded) == 12 * size, "Compressed output did not decode to twelve real frames"
        for index in range(12):
            red, green, blue = decoded[index * size:index * size + 3]
            assert (red > 180 and blue < 60) if index % 2 == 0 else (blue > 180 and red < 60), "Encoded pixels did not preserve alternating EGL colors"
        print("PASS twelve compressed frames decode to the actual alternating EGL red/blue pixels")


if __name__ == "__main__":
    main()

"""Controlled synthetic native decode, JNI transfer, latch, and preview-scale timing."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

CPP = r'''
#import <AVFoundation/AVFoundation.h>
#import <CoreVideo/CoreVideo.h>
#include <jni.h>
#include <cmath>
#include <cstdint>
#include <vector>
#include <cstdlib>
#include <cstdio>
#include <mutex>
static JavaVM* g_touch_vm;
extern "C" float macapk_audio_master_volume(){return 0;}
#include "player.inc"
#include "offer.inc"
extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm,void*){g_touch_vm=vm;return JNI_VERSION_21;}
extern "C" JNIEXPORT jlong JNICALL Java_FrameBenchmark_open(JNIEnv* e,jclass c,jstring p){return PlayerVideoOpen(e,c,p);}
extern "C" JNIEXPORT jlongArray JNICALL Java_FrameBenchmark_info(JNIEnv* e,jclass c,jlong h){return PlayerVideoInfo(e,c,h);}
extern "C" JNIEXPORT jlongArray JNICALL Java_FrameBenchmark_frame(JNIEnv* e,jclass c,jlong h){return PlayerVideoFrame(e,c,h);}
extern "C" JNIEXPORT void JNICALL Java_FrameBenchmark_play(JNIEnv* e,jclass c,jlong h){PlayerVideoCommand(e,c,h,1,1);}
extern "C" JNIEXPORT jboolean JNICALL Java_FrameBenchmark_offer(JNIEnv*,jclass,jlong h){return MacapkOfferDecodedFrameToTextureView((void*)(uintptr_t)h);}
extern "C" JNIEXPORT void JNICALL Java_FrameBenchmark_release(JNIEnv*,jclass,jlong h){CFRelease((CVPixelBufferRef)(uintptr_t)h);}
extern "C" JNIEXPORT void JNICALL Java_FrameBenchmark_close(JNIEnv* e,jclass c,jlong h){PlayerVideoClose(e,c,h);}
'''

JAVA = r'''
import android.graphics.*;
import java.util.*;
public final class FrameBenchmark {
 static native long open(String path);static native long[] info(long h);static native long[] frame(long h);
 static native void play(long h);static native boolean offer(long h);static native void release(long h);static native void close(long h);
 static long hash(Bitmap b){long h=1;for(int y=1;y<9;y++)for(int x=1;x<9;x++)h=h*31+b.getPixel(b.getWidth()*x/10,b.getHeight()*y/10);return h;}
 static double p(List<Long> values,double q){var sorted=new ArrayList<>(values);Collections.sort(sorted);return sorted.get(Math.min(sorted.size()-1,(int)(sorted.size()*q)))/1e6;}
 public static void main(String[] args)throws Exception{
  System.load(args[0]);
  for(int round=0;round<5;round++)for(int mode=0;mode<2;mode++){
   String path=args[mode+1];long h=open(path);if(h==0)throw new AssertionError("open");
   long deadline=System.nanoTime()+5_000_000_000L;long[] metadata;
   do{metadata=info(h);if(metadata[3]<0)throw new AssertionError("prepare");if(metadata[3]==1)break;Thread.sleep(2);}while(System.nanoTime()<deadline);
   if(metadata[3]!=1)throw new AssertionError("prepare timeout");
   var target=new SurfaceTexture(false);target.macapkRegisterVideoTarget();
   var sink=Bitmap.createBitmap(645,363,Bitmap.Config.ARGB_8888);var canvas=new Canvas(sink);var paint=new Paint();paint.setFilterBitmap(true);
   var transfer=new ArrayList<Long>();var latch=new ArrayList<Long>();var scale=new ArrayList<Long>();var gaps=new ArrayList<Long>();var hashes=new HashSet<Long>();
   var allocation=(com.sun.management.ThreadMXBean)java.lang.management.ManagementFactory.getThreadMXBean();
   long allocatedBefore=allocation.getThreadAllocatedBytes(Thread.currentThread().threadId());
   long gcBefore=java.lang.management.ManagementFactory.getGarbageCollectorMXBeans().stream().mapToLong(b->Math.max(0,b.getCollectionTime())).sum();
   var process=(com.sun.management.OperatingSystemMXBean)java.lang.management.ManagementFactory.getOperatingSystemMXBean();long cpuBefore=process.getProcessCpuTime();
   play(h);long start=System.nanoTime(),previous=0;int errors=0;long copied=0;
   while(System.nanoTime()-start<1_400_000_000L){
    long before=System.nanoTime();long[] frame=frame(h);if(frame==null){Thread.sleep(1);continue;}
    if(previous!=0)gaps.add(before-previous);previous=before;
    long a=System.nanoTime();boolean accepted=offer(frame[0]);long b=System.nanoTime();
    Bitmap bitmap=target.macapkLatchBitmap();long c=System.nanoTime();
    if(!accepted||bitmap==null){errors++;release(frame[0]);continue;}
    canvas.drawBitmap(bitmap,null,new Rect(0,0,645,363),paint);long d=System.nanoTime();
    hashes.add(hash(sink));transfer.add(b-a);latch.add(c-b);scale.add(d-c);copied+=frame[1]*frame[2]*4;
    release(frame[0]);
   }
   long allocated=allocation.getThreadAllocatedBytes(Thread.currentThread().threadId())-allocatedBefore;
   long gc=java.lang.management.ManagementFactory.getGarbageCollectorMXBeans().stream().mapToLong(b->Math.max(0,b.getCollectionTime())).sum()-gcBefore;
   double cpu=(process.getProcessCpuTime()-cpuBefore)/1e6;
   close(h);target.release();sink.recycle();
   if(errors!=0||transfer.size()<15||hashes.size()<3)throw new AssertionError("invalid work count="+transfer.size()+" hashes="+hashes.size()+" errors="+errors);
   System.out.printf(java.util.Locale.ROOT,"RESULT mode=%s run=%d frames=%d hashes=%d errors=%d MB=%.1f alloc_MB=%.1f gc_ms=%d cpu_ms=%.1f transfer_ms=%.3f latch_ms=%.3f scale_ms=%.3f gap_p95_ms=%.3f gap_max_ms=%.3f%n",mode==0?"1080p":"4K",round,transfer.size(),hashes.size(),errors,copied/1e6,allocated/1e6,gc,cpu,p(transfer,.5),p(latch,.5),p(scale,.5),p(gaps,.95),p(gaps,1));
   if(allocated>200_000_000L)throw new AssertionError("frame transfer exceeded 200 MB allocation ceiling");
  }
 }
}
'''

OWNERSHIP = r'''
package android.graphics;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
public final class FrameBufferOwnershipTest {
 static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 static SurfaceTexture target(){var t=new SurfaceTexture(false);t.macapkRegisterVideoTarget();return t;}
 static SurfaceTexture.DecodedFrameBuffer acquire(int n){var lease=SurfaceTexture.macapkAcquireDecodedFrameBuffer(n);check(lease!=null,"no free buffer");return lease;}
 static void offer(SurfaceTexture.DecodedFrameBuffer b,int w,int h){check(SurfaceTexture.macapkOfferDecodedFrameBuffer(b,w,h,w),"offer failed");}
 static void fill(SurfaceTexture.DecodedFrameBuffer b,int color){Arrays.fill(b.pixels,color);}
 static final class BlockingImage extends java.awt.image.BufferedImage {
  BlockingImage(){super(2,2,java.awt.image.BufferedImage.TYPE_INT_ARGB);}
  final CountDownLatch entered=new CountDownLatch(1),proceed=new CountDownLatch(1);
  @Override public void setRGB(int x,int y,int w,int h,int[] pixels,int offset,int stride){
   entered.countDown();try{check(proceed.await(3,TimeUnit.SECONDS),"blocked latch timeout");}catch(InterruptedException e){throw new AssertionError(e);}
   super.setRGB(x,y,w,h,pixels,offset,stride);
  }
 }
 public static void main(String[] args)throws Exception{
  var t=target();var a=acquire(4);var b=acquire(4);check(a.pixels!=b.pixels,"same buffer leased twice");
  check(SurfaceTexture.macapkAcquireDecodedFrameBuffer(4)==null,"more than two buffers leased");
  fill(a,11);fill(b,22);offer(a,2,2);offer(b,2,2); // b supersedes a.
  var c=acquire(4);check(c.pixels==a.pixels,"superseded buffer not returned");fill(c,33);
  check(t.macapkLatchBitmap().getPixel(0,0)==22,"pending frame was overwritten");
  offer(c,2,2);check(t.macapkLatchBitmap().getPixel(0,0)==33,"reused frame not copied");
  offer(a,2,2);check(t.macapkLatchBitmap().getPixel(0,0)==33,"old lease queued twice");
  var stale=acquire(4);var resized=acquire(9);fill(stale,44);fill(resized,99);offer(stale,2,2);offer(resized,3,3);
  var image=t.macapkLatchBitmap();check(image.getWidth()==3&&image.getHeight()==3&&image.getPixel(2,2)==99,"resize output changed");
  var wrongTarget=acquire(9);fill(wrongTarget,55);var other=target();offer(wrongTarget,3,3);
  check(other.macapkLatchBitmap()==null,"frame routed to another target");
  t.release();other.release();
  var released=target();var held=acquire(4);released.release();offer(held,2,2);
  check(SurfaceTexture.macapkAcquireDecodedFrameBuffer(4)==null,"released target accepted a lease");
  var concurrent=target();var first=acquire(4);fill(first,66);offer(first,2,2);
  var blocker=Bitmap.createBitmap(2,2,Bitmap.Config.ARGB_8888);var blockingImage=new BlockingImage();blocker.macapkSetAwtImage(blockingImage);
  var field=SurfaceTexture.class.getDeclaredField("mLatchBitmap");field.setAccessible(true);field.set(concurrent,blocker);
  var error=new AtomicReference<Throwable>();Thread latch=new Thread(()->{try{concurrent.macapkLatchBitmap();}catch(Throwable e){error.set(e);}});
  latch.start();check(blockingImage.entered.await(3,TimeUnit.SECONDS),"latch did not enter");
  var second=acquire(4);fill(second,77);offer(second,2,2);
  check(SurfaceTexture.macapkAcquireDecodedFrameBuffer(4)==null,"latching buffer returned before copy completed");
  check(first.pixels[0]==66,"producer changed latching pixels");blockingImage.proceed.countDown();latch.join(3000);
  check(!latch.isAlive()&&error.get()==null,"consumer failed");check(blocker.getPixel(0,0)==66,"latched bitmap corrupted");
  var after=acquire(4);check(after.pixels==first.pixels,"consumed buffer not returned");fill(after,88);
  check(blocker.getPixel(0,0)==66,"producer mutated consumed bitmap");
  check(concurrent.macapkLatchBitmap().getPixel(0,0)==77,"pending second frame corrupted");offer(after,2,2);
  check(concurrent.macapkLatchBitmap().getPixel(0,0)==88,"post-latch reuse failed");concurrent.release();
  var cancellation=target();var cancelled=acquire(4);cancelled.cancel();var replacement=acquire(4);
  check(cancelled.pixels==replacement.pixels,"cancelled producer lease not returned");replacement.cancel();cancellation.release();
  var releasing=target();var last=acquire(4);fill(last,111);offer(last,2,2);
  var releasingBitmap=Bitmap.createBitmap(2,2,Bitmap.Config.ARGB_8888);var releasingImage=new BlockingImage();releasingBitmap.macapkSetAwtImage(releasingImage);field.set(releasing,releasingBitmap);
  var result=new AtomicReference<Bitmap>();Thread releasingLatch=new Thread(()->{try{result.set(releasing.macapkLatchBitmap());}catch(Throwable e){error.set(e);}});
  releasingLatch.start();check(releasingImage.entered.await(3,TimeUnit.SECONDS),"release latch did not enter");releasing.release();releasingImage.proceed.countDown();releasingLatch.join(3000);
  check(!releasingLatch.isAlive()&&error.get()==null&&result.get()==null,"release raced consumer unsafely");
  System.out.println("PASS pool: two buffers, supersede, duplicate lease, resize, target identity, release, concurrent latch ownership");
 }
}
'''


def run(args, **kwargs):
    result = subprocess.run([str(x) for x in args], timeout=180, **kwargs)
    if result.returncode:
        if kwargs.get("capture_output"):
            print(result.stdout or "", end="")
            print(result.stderr or "", end="")
        raise SystemExit("Frame transfer test failed")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--jdk-home", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--baseline-offer", type=Path, help="Run the allocation assertion against an older Cocoa source function")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="frame-bench-", dir=args.work_root) as temporary:
        root = Path(temporary)
        source, jdk = args.source, args.jdk_home
        code = (source / "runtime/src/video_toolbox.mm").read_text().split("// BEGIN mediaplayer-file-video", 1)[1].split("// END mediaplayer-file-video", 1)[0]
        (root / "player.inc").write_text(code)
        code = (args.baseline_offer or source / "runtime/src/cocoa_bridge.mm").read_text()
        start = code.index("static bool MacapkOfferDecodedFrameToTextureView(void* pixbuf)")
        end = code.index("    return offered;\n}", start) + len("    return offered;\n}")
        (root / "offer.inc").write_text(code[start:end])
        (root / "bridge.mm").write_text(CPP)
        (root / "FrameBenchmark.java").write_text(JAVA)
        (root / "FrameBufferOwnershipTest.java").write_text(OWNERSHIP)
        for name, size in (("1080p", "1920x1080"), ("4k", "3840x2160")):
            run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size="+size+":rate=30", "-t", "3", "-an", "-c:v", "h264_videotoolbox", "-b:v", "20M", root / (name+".mp4")])
        run(["clang++", "-dynamiclib", "-O2", "-std=c++17", "-fno-objc-arc", "-Wno-deprecated-declarations",
             "-I"+str(root), "-I"+str(source / "runtime/src"), "-I"+str(jdk / "include"), "-I"+str(jdk / "include/darwin"),
             root / "bridge.mm", "-framework", "AppKit", "-framework", "AVFoundation", "-framework", "CoreMedia", "-framework", "CoreVideo", "-o", root / "bridge.dylib"])
        classpath = str(source / "runtime/build/lib/android-framework.jar")+":"+str(source / "runtime/build/lib/macapk-loader.jar")
        run([jdk / "bin/javac", "-cp", classpath, "-d", root,
             source / "runtime/java/android/graphics/SurfaceTexture.java", root / "FrameBenchmark.java", root / "FrameBufferOwnershipTest.java"])
        env = dict(os.environ, MACAPK_LOG_LEVEL="99", MACAPK_AUDIO_MUTE="1")
        run([jdk / "bin/java", "-Djava.awt.headless=true", "-cp", str(root)+":"+classpath,
             "android.graphics.FrameBufferOwnershipTest"], env=env)
        result = run([jdk / "bin/java", "-Xmx1g", "-Djava.awt.headless=true", "-cp", str(root)+":"+classpath,
                      "FrameBenchmark", root / "bridge.dylib", root / "1080p.mp4", root / "4k.mp4"], env=env, text=True, capture_output=True)
        print(result.stdout, end="")
        (args.work_root / "frame-transfer-results.txt").write_text(result.stdout)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check Camera2 JPEG delivery using synthetic pixels, without camera hardware."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

BRIDGE = r'''
#include <jni.h>
#include <vector>
static int copies=0,opens=0;static bool available=true,stable=false,held=false;static jlong timestamp=0;
static jint count(JNIEnv*,jclass){return 1;}
static jint formatCount(JNIEnv*,jclass,jint){return 1;}
static jstring name(JNIEnv*e,jclass,jint){return e->NewStringUTF("synthetic-camera");}
static jint zero(JNIEnv*,jclass,jint){return 0;}
static jint width(JNIEnv*,jclass,jint,jint){return 64;}
static jint height(JNIEnv*,jclass,jint,jint){return 48;}
static jdouble fps(JNIEnv*,jclass,jint,jint){return 30;}
static jlong openCamera(JNIEnv*,jclass,jint){opens++;return 0;}
static jlong copy(JNIEnv*e,jclass,jlong,jintArray output,jintArray dims){
 if(!available)return 0;copies++;timestamp=123456789LL+copies*1000000LL;
 std::vector<jint> pixels(64*48);
 for(int y=0;y<48;y++)for(int x=0;x<64;x++)pixels[y*64+x]=(jint)(y<8?((stable||copies%2)?0xff00ff00u:0xffffffffu):(x<32?0xffff0000u:0xff0000ffu));
 if(e->GetArrayLength(output)<(jsize)pixels.size())return 0;
 jint size[]={64,48};e->SetIntArrayRegion(output,0,pixels.size(),pixels.data());e->SetIntArrayRegion(dims,0,2,size);return timestamp;
}
static jint copied(JNIEnv*,jclass){return copies;}
static jint opened(JNIEnv*,jclass){return opens;}
static jlong lastTime(JNIEnv*,jclass){return timestamp;}
static void haveFrame(JNIEnv*,jclass,jboolean value){available=value;}
static void stablePixels(JNIEnv*,jclass,jboolean value){stable=value;}
static jboolean acquire(JNIEnv*,jclass,jlong){if(held)return false;held=true;return true;}
static void release(JNIEnv*,jclass,jlong){held=false;}
static jboolean isHeld(JNIEnv*,jclass){return held;}
static jint imageWidth(JNIEnv*,jclass,jlong){return 64;}
static jint imageHeight(JNIEnv*,jclass,jlong){return 48;}
static jint rowStride(JNIEnv*,jclass,jlong,jint){return 64;}
static jint pixelStride(JNIEnv*,jclass,jlong,jint plane){return plane==0?1:2;}
static jlong frameTime(JNIEnv*,jclass,jlong){return 987654321;}
static jobject plane(JNIEnv*e,jclass,jlong,jint index){static unsigned char y[64*48]={},uv[64*24]={};return index==0?e->NewDirectByteBuffer(y,sizeof(y)):e->NewDirectByteBuffer(uv+(index==2?1:0),sizeof(uv)-(index==2?1:0));}
extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM*vm,void*){
 JNIEnv*e=nullptr;if(vm->GetEnv((void**)&e,JNI_VERSION_21)!=JNI_OK)return JNI_ERR;
 jclass camera=e->FindClass("com/macapk/loader/CameraBridge");
 JNINativeMethod methods[]={
 {(char*)"nativeDeviceCount",(char*)"()I",(void*)count},
 {(char*)"nativeDeviceId",(char*)"(I)Ljava/lang/String;",(void*)name},
 {(char*)"nativeDeviceName",(char*)"(I)Ljava/lang/String;",(void*)name},
 {(char*)"nativeDeviceFacing",(char*)"(I)I",(void*)zero},
 {(char*)"nativeDeviceSensorOrientation",(char*)"(I)I",(void*)zero},
 {(char*)"nativeFormatCount",(char*)"(I)I",(void*)formatCount},
 {(char*)"nativeFormatWidth",(char*)"(II)I",(void*)width},
 {(char*)"nativeFormatHeight",(char*)"(II)I",(void*)height},
 {(char*)"nativeFormatMinFps",(char*)"(II)D",(void*)fps},
 {(char*)"nativeFormatMaxFps",(char*)"(II)D",(void*)fps},
 {(char*)"nativeOpen",(char*)"(I)J",(void*)openCamera},
 {(char*)"nativeCopyLatestArgb",(char*)"(J[I[I)J",(void*)copy},
 {(char*)"nativeAcquire",(char*)"(J)Z",(void*)acquire},{(char*)"nativeRelease",(char*)"(J)V",(void*)release},
 {(char*)"nativeWidth",(char*)"(J)I",(void*)imageWidth},{(char*)"nativeHeight",(char*)"(J)I",(void*)imageHeight},
 {(char*)"nativeRowStride",(char*)"(JI)I",(void*)rowStride},{(char*)"nativePixelStride",(char*)"(JI)I",(void*)pixelStride},
 {(char*)"nativeFrameTimestamp",(char*)"(J)J",(void*)frameTime},{(char*)"nativePlaneBuffer",(char*)"(JI)Ljava/nio/ByteBuffer;",(void*)plane}};
 if(!camera||e->RegisterNatives(camera,methods,sizeof(methods)/sizeof(methods[0]))!=JNI_OK)return JNI_ERR;
 jclass test=e->FindClass("android/hardware/camera2/CameraJpegContract");
 JNINativeMethod probes[]={{(char*)"copies",(char*)"()I",(void*)copied},{(char*)"opens",(char*)"()I",(void*)opened},
 {(char*)"lastTimestamp",(char*)"()J",(void*)lastTime},{(char*)"haveFrame",(char*)"(Z)V",(void*)haveFrame},
 {(char*)"stablePixels",(char*)"(Z)V",(void*)stablePixels},{(char*)"held",(char*)"()Z",(void*)isHeld}};
 return test&&e->RegisterNatives(test,probes,6)==JNI_OK?JNI_VERSION_21:JNI_ERR;
}
'''

JAVA = r'''
package android.hardware.camera2;
import android.graphics.ImageFormat;
import android.media.*;
import android.os.*;
import android.view.Surface;
import java.util.*;
public final class CameraJpegContract {
 static native int copies();static native int opens();static native long lastTimestamp();static native void haveFrame(boolean value);static native void stablePixels(boolean value);static native boolean held();
 static Throwable failure;
 static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}
 static CaptureRequest request(Surface surface,int quality,int orientation){
  CaptureRequest.Builder b=new CaptureRequest.Builder();b.addTarget(surface);
  b.set(CaptureRequest.JPEG_QUALITY,(byte)quality);b.set(CaptureRequest.JPEG_ORIENTATION,orientation);return b.build();
 }
 static byte[] bytes(Image image)throws Exception{
  check(image.getFormat()==ImageFormat.JPEG&&image.getPlanes().length==1,"JPEG must have one plane");
  Image.Plane plane=image.getPlanes()[0];check(plane.getRowStride()==0&&plane.getPixelStride()==0,"JPEG strides must be zero");
  var data=plane.getBuffer().duplicate();check(data.isDirect(),"JPEG plane must be direct");byte[] bytes=new byte[data.remaining()];data.get(bytes);
  var decoded=javax.imageio.ImageIO.read(new java.io.ByteArrayInputStream(bytes));
  check(decoded!=null&&decoded.getWidth()==image.getWidth()&&decoded.getHeight()==image.getHeight(),"JPEG bytes and image dimensions disagree");
  return bytes;
 }
 static void closed(Image image){try{image.getPlanes();throw new AssertionError("closed image remained readable");}catch(IllegalStateException expected){}}
 static void exercise()throws Exception{
  var characteristics=new CameraManager().getCameraCharacteristics("0");
  var map=characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
  var sizes=map.getOutputSizes(ImageFormat.JPEG);
  check(sizes!=null&&sizes.length==1&&sizes[0].getWidth()==64&&sizes[0].getHeight()==48,"JPEG sizes must come from advertised synthetic device format");
  check(map.getOutputSizes(ImageFormat.RAW_SENSOR)==null,"unsupported format was invented");
  ImageReader jpeg=ImageReader.newInstance(64,48,ImageFormat.JPEG,2);
  ImageReader yuv=ImageReader.newInstance(64,48,ImageFormat.YUV_420_888,2);
  jpeg.macapkAttachCameraSource(1,64,48);yuv.macapkAttachCameraSource(1,64,48);
  Thread owner=Thread.currentThread();int[] callbacks={0};
  jpeg.setOnImageAvailableListener(reader->{try{check(Thread.currentThread()==owner,"wrong callback thread");callbacks[0]++;}catch(Throwable error){failure=error;}},new Handler(Looper.myLooper()));
  jpeg.macapkOnCameraFrame();check(copies()==0&&jpeg.acquireNextImage()==null,"untargeted JPEG preview encoded pixels");
  CameraCaptureSessionImpl.dispatchImageReaders(request(yuv.getSurface(),90,0),List.of(jpeg,yuv));
  check(copies()==0&&jpeg.acquireNextImage()==null,"YUV-only request encoded JPEG");
  var capture=request(jpeg.getSurface(),90,0);
  CameraCaptureSessionImpl.dispatchImageReaders(capture,List.of(jpeg,yuv));
  Image first=jpeg.acquireNextImage();check(first!=null&&first.getTimestamp()==lastTimestamp(),"missing JPEG or fabricated timestamp");
  byte[] firstBytes=bytes(first);var pixels=javax.imageio.ImageIO.read(new java.io.ByteArrayInputStream(firstBytes));
  check(((pixels.getRGB(16,24)>>16)&255)>200&&(pixels.getRGB(48,24)&255)>200,"JPEG lost synthetic red/blue pixels");
  CameraCaptureSessionImpl.dispatchImageReaders(capture,List.of(jpeg,yuv));Image second=jpeg.acquireNextImage();check(second!=null,"second JPEG missing");
  check(Arrays.equals(firstBytes,bytes(first)),"next frame overwrote a held JPEG plane");
  int before=copies();CameraCaptureSessionImpl.dispatchImageReaders(capture,List.of(jpeg,yuv));check(copies()==before,"maxImages did not bound encoding");
  first.close();closed(first);second.close();
  CameraCaptureSessionImpl.dispatchImageReaders(request(jpeg.getSurface(),95,90),List.of(jpeg,yuv));
  Image rotated=jpeg.acquireLatestImage();check(rotated!=null&&rotated.getWidth()==48&&rotated.getHeight()==64,"orientation did not rotate encoded pixels");
  var rotatedPixels=javax.imageio.ImageIO.read(new java.io.ByteArrayInputStream(bytes(rotated)));
  check(((rotatedPixels.getRGB(24,16)>>16)&255)>200&&(rotatedPixels.getRGB(24,48)&255)>200,"orientation changed dimensions without rotating pixels");rotated.close();
  stablePixels(true);
  CameraCaptureSessionImpl.dispatchImageReaders(request(jpeg.getSurface(),10,0),List.of(jpeg,yuv));Image low=jpeg.acquireNextImage();byte[] lowBytes=bytes(low);low.close();
  CameraCaptureSessionImpl.dispatchImageReaders(request(jpeg.getSurface(),95,0),List.of(jpeg,yuv));Image high=jpeg.acquireNextImage();byte[] highBytes=bytes(high);high.close();
  check(!Arrays.equals(lowBytes,highBytes),"JPEG quality was ignored");
  stablePixels(false);
  haveFrame(false);CameraCaptureSessionImpl.dispatchImageReaders(capture,List.of(jpeg,yuv));check(jpeg.acquireNextImage()==null,"missing source frame produced an image");haveFrame(true);
  CameraCaptureSessionImpl.dispatchImageReaders(capture,List.of(jpeg,yuv));
  CameraCaptureSessionImpl.dispatchImageReaders(capture,List.of(jpeg,yuv));
  Image latest=jpeg.acquireLatestImage();check(latest!=null&&latest.getTimestamp()==lastTimestamp(),"acquireLatest did not drop older pending image");latest.close();
  check(opens()==0,"test opened camera hardware");
  check(!held(),"JPEG retained a native frame");
  new Handler(Looper.myLooper()).post(()->{try{
   check(callbacks[0]>0,"JPEG availability callback missing");
   CameraCaptureSessionImpl.dispatchImageReaders(capture,List.of(jpeg,yuv));jpeg.macapkAttachCameraSource(2,64,48);check(jpeg.acquireNextImage()==null,"replacement source kept pending JPEG");
   CameraCaptureSessionImpl.dispatchImageReaders(capture,List.of(jpeg,yuv));Image replaced=jpeg.acquireNextImage();check(replaced!=null,"replacement source did not deliver");jpeg.macapkAttachCameraSource(3,64,48);closed(replaced);
   CameraCaptureSessionImpl.dispatchImageReaders(capture,List.of(jpeg,yuv));jpeg.macapkDetachCameraSource();check(jpeg.acquireNextImage()==null,"detach kept a pending JPEG");
   Image yuvImage=yuv.acquireNextImage();check(yuvImage!=null&&held()&&yuvImage.getPlanes().length==3,"synthetic YUV acquire failed");yuv.macapkDetachCameraSource();check(!held(),"detach leaked native YUV frame");closed(yuvImage);
   jpeg.close();try{jpeg.macapkAttachCameraSource(4,64,48);throw new AssertionError("closed reader accepted source");}catch(IllegalStateException expected){}
  }catch(Throwable error){failure=error;}finally{jpeg.close();yuv.close();Looper.myLooper().quit();}});
 }
 public static void main(String[]args)throws Exception{
  System.load(args[0]);Looper.prepareMainLooper();
  Thread worker=new Thread(()->{try{Looper.prepare();exercise();Looper.loop();}catch(Throwable error){failure=error;}},"synthetic-camera-owner");
  worker.start();worker.join(10000);if(worker.isAlive()){worker.interrupt();throw new AssertionError("camera fixture deadline");}
  if(failure!=null)throw new AssertionError("synthetic Camera2 JPEG contract",failure);
  System.out.println("PASS synthetic JPEG pixels/metadata/direct plane, request targets, quality/orientation, bounded images, detach and owner callbacks; no camera opened");
 }
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True,type=Path)
    parser.add_argument("--jdk-home",required=True,type=Path)
    parser.add_argument("--work-root",required=True,type=Path)
    parser.add_argument("--source-overlay",action="store_true")
    args=parser.parse_args();source=args.source.resolve();jdk=args.jdk_home.resolve();args.work_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="camera-jpeg-contract-",dir=args.work_root) as temporary:
        work=Path(temporary);(work/"bridge.cpp").write_text(BRIDGE);(work/"CameraJpegContract.java").write_text(JAVA)
        subprocess.run(["clang++","-dynamiclib","-std=c++17","-I"+str(jdk/"include"),"-I"+str(jdk/"include/darwin"),str(work/"bridge.cpp"),"-o",str(work/"camera.dylib")],check=True,timeout=30)
        cp=os.pathsep.join(str(source/"runtime/build/lib"/name) for name in ("android-framework.jar","macapk-loader.jar"))
        files=[str(work/"CameraJpegContract.java")]
        if args.source_overlay:
            files += [str(source/"runtime/java"/name) for name in ("android/media/ImageReader.java","android/hardware/camera2/CameraBackend.java","android/hardware/camera2/CameraCaptureSessionImpl.java","android/hardware/camera2/params/StreamConfigurationMap.java")]
        subprocess.run([str(jdk/"bin/javac"),"-cp",cp,"-d",str(work),*files],check=True,timeout=40)
        subprocess.run([str(jdk/"bin/java"),"-Djava.awt.headless=true","-cp",str(work)+os.pathsep+cp,"android.hardware.camera2.CameraJpegContract",str(work/"camera.dylib")],env=dict(os.environ,MACAPK_LOG_LEVEL="99"),check=True,timeout=15)


if __name__=="__main__":main()

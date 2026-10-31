#!/usr/bin/env python3
"""Compare real native extraction from an owned MOV and selected content URI."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

BRIDGE = r'''#include <jni.h>
namespace macapk {void RegisterDocumentPickerMethods(JNIEnv*);namespace osnative{void RegisterNativeOsMethods(JNIEnv*);}namespace media{void RegisterNativeMediaMethods(JNIEnv*);}}
namespace macapk {namespace video{void RegisterNativeVideoMethods(JNIEnv*);}}
extern "C" float macapk_audio_master_volume(){return 0;}
extern "C" void CocoaPresentVideoFrame(void*,int,int){}
extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm,void*){JNIEnv* e=nullptr;if(vm->GetEnv((void**)&e,JNI_VERSION_21)!=JNI_OK)return JNI_ERR;macapk::RegisterDocumentPickerMethods(e);macapk::osnative::RegisterNativeOsMethods(e);macapk::media::RegisterNativeMediaMethods(e);macapk::video::RegisterNativeVideoMethods(e);return JNI_VERSION_21;}
'''

JAVA = r'''package com.macapk.loader;
import android.content.*;import android.content.pm.ProviderInfo;import android.content.res.Resources;
import android.media.*;import android.net.Uri;import android.provider.*;import com.macapk.loader.*;
import java.nio.*;import java.nio.file.*;import java.util.*;
public class ContentExtractorContract {
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 static byte[] sample(MediaExtractor e){ByteBuffer b=ByteBuffer.allocate(262144);int n=e.readSampleData(b,0);check(n>0,"native sample missing");return Arrays.copyOf(b.array(),n);}
 static void preparePlayer(Context context,Uri source,String alias,boolean content)throws Exception{
  var done=new java.util.concurrent.CountDownLatch(1);var result=new java.util.concurrent.atomic.AtomicReference<Throwable>();
  Thread owner=new Thread(()->{try{
   android.os.Looper.prepare();android.os.Looper loop=android.os.Looper.myLooper();android.os.Handler handler=new android.os.Handler(loop);MediaPlayer player=new MediaPlayer();
   Runnable finish=()->{player.release();loop.quit();done.countDown();};
   player.setOnPreparedListener(p->{try{check(Thread.currentThread().getName().equals("owned-player-owner"),"prepared callback used wrong owner");check(p.getVideoWidth()==64&&p.getVideoHeight()==48&&p.getDuration()>0,"prepared dimensions/duration missing");}catch(Throwable failure){result.set(failure);}finally{finish.run();}});
   player.setOnErrorListener((p,what,extra)->{result.set(new AssertionError("native prepare returned error "+what));finish.run();return true;});
   if(content)player.setDataSource(context,source);else player.setDataSource(alias);
   player.prepareAsync();handler.postDelayed(()->{result.compareAndSet(null,new AssertionError("native prepare callback timed out"));finish.run();},10000);
   android.os.Looper.loop();
  }catch(Throwable failure){result.set(failure);done.countDown();}},"owned-player-owner");owner.setDaemon(true);owner.start();
  check(done.await(11,java.util.concurrent.TimeUnit.SECONDS),"player owner did not exit");owner.join(1000);if(result.get()!=null)throw new AssertionError(content?"content MediaPlayer preparation failed":"alias MediaPlayer preparation failed",result.get());
  System.out.println(content?"PASS real MediaPlayer content URI prepares with dimensions on owner looper":"PASS real MediaPlayer selected alias prepares with dimensions on owner looper");
 }
 static void decode(Context context,Uri source,boolean video)throws Exception{
  MediaExtractor input=new MediaExtractor();input.setDataSource(context,source,null);int track=-1;
  for(int i=0;i<input.getTrackCount();i++)if(input.getTrackFormat(i).getString("mime").startsWith(video?"video/":"audio/")){track=i;break;}
  check(track>=0,"real requested track missing");MediaFormat format=input.getTrackFormat(track);input.selectTrack(track);
  MediaCodec codec=MediaCodec.createDecoderByType(format.getString("mime"));codec.configure(format,null,null,0);codec.start();
  boolean eos=false,finished=false;int decoded=0;Set<Long> hashes=new HashSet<>();long deadline=System.nanoTime()+8_000_000_000L;MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();
  try{while(!finished&&System.nanoTime()<deadline){
   if(!eos){int index=codec.dequeueInputBuffer(1000);if(index>=0){ByteBuffer buffer=codec.getInputBuffer(index);int n=input.readSampleData(buffer,0);long pts=input.getSampleTime();
    if(n<0){codec.queueInputBuffer(index,0,0,0,MediaCodec.BUFFER_FLAG_END_OF_STREAM);eos=true;}else{codec.queueInputBuffer(index,0,n,pts,0);input.advance();}}}
   int output=codec.dequeueOutputBuffer(info,1000);if(output>=0){
    if(video){try(Image image=codec.getOutputImage(output)){if(image!=null){ByteBuffer pixels=image.getPlanes()[0].getBuffer().duplicate();java.util.zip.CRC32 hash=new java.util.zip.CRC32();while(pixels.hasRemaining())hash.update(pixels.get());hashes.add(hash.getValue());decoded++;}}}
    else if(info.size>0){ByteBuffer pcm=codec.getOutputBuffer(output);check(pcm!=null&&pcm.remaining()>0,"AAC produced no PCM");decoded+=info.size;}
    finished=(info.flags&MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0;codec.releaseOutputBuffer(output,false);
   }
  }}finally{codec.stop();codec.release();input.release();}
  check(finished,"decoder did not reach end of stream");check(decoded>0,"no actual decoded output");if(video)check(hashes.size()>1,"decoded video pixels did not change");
  System.out.println(video?"PASS actual extracted AVC access units decode to changing video pixels":"PASS actual extracted AAC packets decode to PCM bytes");
 }
 public static void main(String[] args)throws Exception{
  System.load(args[0]);Path root=Path.of(args[1]),original=root.resolve("owned clip.mov");byte[] before=Files.readAllBytes(original);
  ContentResolver resolver=new ContentResolver();Context context=new Context(){
   public String getPackageName(){return "com.instagram.android";}public Resources getResources(){return new Resources(null,null,null);}
   public android.content.res.AssetManager getAssets(){return null;}public Context getApplicationContext(){return this;}
   public ClassLoader getClassLoader(){return getClass().getClassLoader();}public java.io.File getFilesDir(){return root.toFile();}
   public java.io.File getCacheDir(){return root.toFile();}public java.io.File getDir(String n,int m){return root.toFile();}public ContentResolver getContentResolver(){return resolver;}
  };
  MediaStoreProvider provider=new MediaStoreProvider();ProviderInfo info=new ProviderInfo();info.authority="media";provider.attachInfo(context,info);check(provider.onCreate(),"provider setup");ContentProviderRegistry.register("media",provider);
  Uri selected=DocumentPickerHandler.importPickedMedia(context,new String[]{original.toString()});check(selected!=null,"owned selection missing");String alias;
  try(var row=resolver.query(selected,new String[]{"_data"},null,null,null)){check(row.moveToFirst(),"owned row missing");alias=row.getString(0);}
  if(args.length>2&&args[2].equals("player")){preparePlayer(context,selected,alias,false);preparePlayer(context,selected,alias,true);provider.shutdown();return;}
  int anchor=Integer.parseInt(alias.substring(8));check(NativeOs.lseek(anchor,7,0)==7,"anchor setup");
  MediaExtractor file=new MediaExtractor();file.setDataSource(original.toString());int tracks=file.getTrackCount();check(tracks>0,"ordinary MOV has no native tracks");
  MediaFormat format=file.getTrackFormat(0);file.selectTrack(0);byte[] expected=sample(file);long time=file.getSampleTime();file.release();
  for(int repeat=0;repeat<4;repeat++){
   MediaExtractor content=new MediaExtractor();content.setDataSource(context,selected,null);
   check(content.getTrackCount()==tracks,"content URI lost native tracks");
   check(Objects.equals(format.getString("mime"),content.getTrackFormat(0).getString("mime")),"content format differs from file");content.selectTrack(0);
   check(Arrays.equals(expected,sample(content))&&content.getSampleTime()==time,"content compressed sample differs");
   check(content.advance()&&content.getSampleTime()>=time,"native reader did not retain its descriptor");
   var temp=MediaExtractor.class.getDeclaredField("mTmpFile");temp.setAccessible(true);check(temp.get(content)==null,"whole selected source copied to temporary file");
   content.release();check(NativeOs.lseek(anchor,0,1)==7,"extractor changed read-only anchor cursor");
  }
  for(Path whole:new Path[]{original,root.resolve("owned audio.m4a")}){
  MediaExtractor baseline=new MediaExtractor();baseline.setDataSource(whole.toString());int wholeTracks=baseline.getTrackCount();baseline.selectTrack(0);byte[] wholeSample=sample(baseline);baseline.release();
  try(var caller=new java.io.FileInputStream(whole.toFile())){
   caller.getChannel().position(11);for(int mode=0;mode<2;mode++){MediaExtractor descriptor=new MediaExtractor();
    if(mode==0)descriptor.setDataSource(caller.getFD());else descriptor.setDataSource(new android.content.res.AssetFileDescriptor(new android.os.ParcelFileDescriptor(caller.getFD()),0,-1));
    check(descriptor.getTrackCount()==wholeTracks,"whole descriptor lost tracks");descriptor.selectTrack(0);check(Arrays.equals(wholeSample,sample(descriptor)),"whole descriptor sample differs");
    var temp=MediaExtractor.class.getDeclaredField("mTmpFile");temp.setAccessible(true);check(temp.get(descriptor)==null,"whole descriptor copied original");descriptor.release();
    check(caller.getFD().valid()&&caller.getChannel().position()==11,"caller descriptor closed or repositioned");
   }
  }
  }
  Path embedded=root.resolve("owned embedded.bin");ByteBuffer region=ByteBuffer.allocate(before.length+48);region.position(32);region.put(before);Files.write(embedded,region.array());
  try(var caller=new java.io.FileInputStream(embedded.toFile())){
   caller.getChannel().position(9);MediaExtractor slice=new MediaExtractor();slice.setDataSource(caller.getFD(),32,before.length);
   check(slice.getTrackCount()==tracks,"embedded slice lost tracks");slice.selectTrack(0);check(Arrays.equals(expected,sample(slice)),"embedded slice sample differs");
   var temp=MediaExtractor.class.getDeclaredField("mTmpFile");temp.setAccessible(true);java.io.File backing=(java.io.File)temp.get(slice);check(backing!=null&&backing.exists(),"embedded slice missing bounded backing");
   slice.release();check(!backing.exists()&&caller.getFD().valid()&&caller.getChannel().position()==9,"slice cleanup changed caller descriptor");
  }
  decode(context,selected,true);decode(context,selected,false);
  try{new MediaExtractor().setDataSource(context,Uri.parse("content://media/external/video/media/999999999"),null);throw new AssertionError("missing content silently accepted");}catch(java.io.IOException expectedFailure){}
  check(Arrays.equals(before,Files.readAllBytes(original)),"selected original changed");provider.shutdown();
  System.out.println("PASS actual MOV file/content native track+sample parity, independent descriptor ownership, four reopenings, no-copy/read-only source");
 }
}'''


def run(args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, timeout=90, **kwargs)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ("source", "jdk-home", "work-root"):
        p.add_argument("--"+flag, required=True, type=Path)
    p.add_argument("--source-overlay", action="store_true")
    p.add_argument("--player-only",action="store_true",help="Check real prepareAsync alias/content APIs without extractor assertions")
    p.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    p.add_argument("--libvpx-prefix",type=Path)
    a=p.parse_args()
    if not a.ffmpeg:p.error("ffmpeg is required to generate the owned fixture")
    vpx=a.libvpx_prefix or Path(subprocess.check_output(["brew","--prefix","libvpx"],text=True).strip())
    a.work_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="extractor-content-",dir=a.work_root) as temporary:
        root=Path(temporary);(root/"bridge.mm").write_text(BRIDGE);(root/"ContentExtractorContract.java").write_text(JAVA)
        run([a.ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","testsrc2=size=64x48:rate=10","-f","lavfi","-i","sine=frequency=400:sample_rate=44100","-t","1","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",root/"owned clip.mov"])
        run([a.ffmpeg,"-hide_banner","-loglevel","error","-i",root/"owned clip.mov","-vn","-c:a","copy",root/"owned audio.m4a"])
        runtime=a.source/"runtime";includes=["-I"+str(a.jdk_home/"include"),"-I"+str(a.jdk_home/"include/darwin")]
        objects=[]
        for path in [runtime/"src"/name for name in ("document_picker.mm","native_os.cpp","native_sqlite.cpp","media_decode.mm","video_toolbox.mm","video_caps_probe.mm","audio_vorbis_decode.mm","video_vp8_decode.mm","video_vp9_decode.mm")]+[root/"bridge.mm"]:
            obj=root/(path.name+".o");objects.append(obj)
            run(["clang++","-c","-std=c++17","-fobjc-arc" if path.name=="document_picker.mm" else "-fno-objc-arc","-Wno-deprecated-declarations",*includes,"-I"+str(runtime/"include"),"-I"+str(vpx/"include"),path,"-o",obj])
        vorbis=root/"stb_vorbis.o";run(["clang","-c","-w",runtime/"thirdparty/stb_vorbis.c","-o",vorbis]);objects.append(vorbis)
        frameworks=[item for name in ("AppKit","UniformTypeIdentifiers","AVFoundation","CoreMedia","CoreVideo","CoreFoundation","ImageIO","AudioToolbox","VideoToolbox","Metal") for item in ("-framework",name)]
        run(["clang++","-dynamiclib",*objects,vpx/"lib/libvpx.a",*frameworks,"-lcompression","-lsqlite3","-o",root/"backend.dylib"])
        cp=os.pathsep.join(str(runtime/"build/lib"/name) for name in ("android-framework.jar","macapk-loader.jar"))
        files=[root/"ContentExtractorContract.java"]
        if a.source_overlay:files.extend([runtime/"java/android/media/MediaExtractor.java",runtime/"java/com/macapk/loader/NativeMedia.java"])
        run([a.jdk_home/"bin/javac","-cp",cp,"-d",root,*files])
        env=dict(os.environ,MACAPK_LOG_LEVEL="99",MACAPK_ANDROID_ROOT=str(root/"android"),MACAPK_PHOTOKIT="0",MACAPK_MEDIASTORE_ACCESS="0")
        mode=["player"] if a.player_only else []
        run([a.jdk_home/"bin/java","--add-opens=java.base/java.io=ALL-UNNAMED","-Djava.awt.headless=true","-cp",str(root)+os.pathsep+cp,"com.macapk.loader.ContentExtractorContract",root/"backend.dylib",root,*mode],env=env)


if __name__=="__main__":main()

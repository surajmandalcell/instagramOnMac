#!/usr/bin/env python3
"""Headless gallery progress, retry, and shadowed video-view field contracts."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.dont_write_bytecode = True
from media_preparation_test import SOURCES as BASE_SOURCES

SOURCES={name:code for name,code in BASE_SOURCES.items() if name not in ("fixture/PreparationContract.java","com/macapk/loader/CameraBridge.java")}
SOURCES.update({
"com/instagram/creation/activity/MediaCaptureActivity.java":'''package com.instagram.creation.activity;public class MediaCaptureActivity extends com.instagram.modal.TransparentModalActivity{public MediaCaptureActivity()throws java.io.IOException{super();}}''',
"com/instagram/common/gallery/Medium.java":'''package com.instagram.common.gallery;public class Medium{public int A0A=3;public String A0e="/dev/fd/owned";}''',
"X/D3A.java":'''package X;import com.instagram.common.gallery.Medium;public class D3A extends android.widget.FrameLayout{public Object A0D=new Item();public D3A(android.content.Context c){super(c);}public static class Item{public Medium A02=new Medium();}}''',
"X/S9Y.java":'''package X;import com.macapk.loader.InstagramMediaPreparationCompat;public class S9Y extends android.view.TextureView{public enum State{IDLE,PREPARING}public android.media.MediaPlayer A00;public Object A02=new Object();public State A03=State.PREPARING;public int teardowns,binds;public S9Y(android.content.Context c){super(c);}public void A02(){teardowns++;if(A00!=null)A00.release();A00=null;A03=State.IDLE;}public void setVideoPath(String path,Object callback){InstagramMediaPreparationCompat.prepareVideoSource(this,path);binds++;A02=callback;A03=State.PREPARING;}}''',
"com/instagram/creation/capture/video/shared/IgCaptureVideoPreviewView.java":'''package com.instagram.creation.capture.video.shared;public class IgCaptureVideoPreviewView extends X.S9Y{public float A00=7;public Object A02=new Object(),A03=new Object();public IgCaptureVideoPreviewView(android.content.Context c){super(c);}}''',
"com/macapk/loader/DocumentPickerHandler.java":'''package com.macapk.loader;public class DocumentPickerHandler{public static boolean macapkIsSelectedMediaReference(String p){return p!=null&&p.startsWith("/dev/fd/");}public static String macapkReadOnlySelectedMedia(String p){return p;}public static long[] macapkReadVideoMetadata(String p){return null;}public static String macapkVideoPath(java.io.FileDescriptor f){return null;}}''',
"com/macapk/loader/MovCompatibilityCache.java":'''package com.macapk.loader;public class MovCompatibilityCache{public enum State{WAITING,RUNNING,READY,FAILED}public record Snapshot(State state,double fraction,String error){}public static Snapshot snapshot=new Snapshot(State.RUNNING,.4,null);public static Snapshot snapshotForSelectedData(String p){return snapshot;}public static boolean sameSelectedSource(String a,String b){return a!=null&&a.equals(b);}}''',
"android/provider/MediaStoreProvider.java":'''package android.provider;public class MediaStoreProvider{public static java.util.concurrent.CompletableFuture<String> next=new java.util.concurrent.CompletableFuture<>();public static java.util.concurrent.CompletableFuture<String> macapkPrepareSelectedVideo(String p){return next;}}''',
"fixture/GalleryContract.java":r'''package fixture;
import android.view.*;import android.widget.*;import android.media.MediaPlayer;import com.macapk.loader.*;
import com.instagram.creation.activity.MediaCaptureActivity;import com.instagram.creation.capture.video.shared.IgCaptureVideoPreviewView;
public class GalleryContract {
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 static Object field(Object object,String name)throws Exception{var f=object.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(object);}
 static Object gallery()throws Exception{var f=InstagramMediaPreparationCompat.class.getDeclaredField("GALLERY");f.setAccessible(true);return f.get(null);}
 static void top(android.app.Activity activity)throws Exception{var f=ActivityHost.class.getDeclaredField("stack");f.setAccessible(true);var stack=(java.util.Deque<android.app.Activity>)f.get(null);stack.clear();stack.push(activity);}
 static void source(MediaPlayer player,String alias)throws Exception{var f=MediaPlayer.class.getDeclaredField("localSource");f.setAccessible(true);f.set(player,alias);}
 static class Signals extends MediaPlayer{PreparationState signal=PreparationState.PREPARING;boolean frame;public PreparationState macapkPreparationState(){return signal;}public boolean macapkHasRenderedVideoFrame(){return frame;}public boolean macapkSourceMatches(String source){return true;}}
 public static void main(String[]args)throws Exception{
  android.os.Looper.prepareMainLooper();MediaCaptureActivity activity=new MediaCaptureActivity();top(activity);
  LinearLayout root=new LinearLayout(activity);root.setOrientation(LinearLayout.VERTICAL);FrameLayout content=new FrameLayout(activity);content.setId(android.R.id.content);root.addView(content,new LinearLayout.LayoutParams(-1,-1));
  var decorField=activity.getWindow().getClass().getDeclaredField("decor");decorField.setAccessible(true);decorField.set(activity.getWindow(),root);
  int widthSpec=View.MeasureSpec.makeMeasureSpec(786,View.MeasureSpec.EXACTLY),heightSpec=View.MeasureSpec.makeMeasureSpec(1702,View.MeasureSpec.EXACTLY);
  root.measure(widthSpec,heightSpec);root.layout(0,0,786,1702);root.macapkDispatchAttachedToWindow();
  X.D3A picker=new X.D3A(activity);content.addView(picker,new FrameLayout.LayoutParams(-1,-1));picker.layout(0,0,786,1702);IgCaptureVideoPreviewView preview=new IgCaptureVideoPreviewView(activity);picker.addView(preview);preview.layout(0,112,786,898);
  Signals player=new Signals();((X.S9Y)preview).A00=player;
  InstagramMediaPreparationCompat.onRootDraw(root);Object gallery=gallery();LinearLayout panel=(LinearLayout)field(gallery,"panel");check(panel!=null,"gallery conversion panel missing behind shadowed float");
  check(((TextView)field(gallery,"message")).getText().toString().contains("40%"),"truthful conversion percentage missing");check(panel.getAccessibilityLiveRegion()==View.ACCESSIBILITY_LIVE_REGION_POLITE,"gallery status accessibility missing");
  check((Long)field(gallery,"deadline")-android.os.SystemClock.uptimeMillis()>600000,"conversion status expires before export budget");
  root.measure(widthSpec,heightSpec);root.layout(0,0,786,1702);check(panel.getParent()==content&&panel.getHeight()>0&&panel.getBottom()<=1702,"vertical decor hides gallery progress controls");
  picker.layout(0,2000,786,3702);check(picker.isShown(),"offscreen retained fixture unexpectedly hidden");InstagramMediaPreparationCompat.onRootDraw(root);check(field(gallery,"panel")==null,"offscreen retained gallery covered viewport");picker.layout(0,0,786,1702);InstagramMediaPreparationCompat.onRootDraw(root);
  MovCompatibilityCache.snapshot=new MovCompatibilityCache.Snapshot(MovCompatibilityCache.State.READY,1,null);InstagramMediaPreparationCompat.onRootDraw(root);check(((TextView)field(gallery,"message")).getText().toString().contains("Preparing"),"ready cache skipped actual preview preparation");
  player.signal=MediaPlayer.PreparationState.FAILED;InstagramMediaPreparationCompat.onRootDraw(root);panel=(LinearLayout)field(gallery,"panel");root.measure(widthSpec,heightSpec);root.layout(0,0,786,1702);check(panel.getHeight()>0,"vertical decor hides gallery error controls");boolean retry=false;for(int i=0;i<panel.getChildCount();i++)if(panel.getChildAt(i) instanceof Button b&&b.getText().toString().equals("Retry")){retry=true;b.performClick();break;}
  check(retry&&preview.teardowns==1&&preview.binds==1,"retry did not use declared S9Y teardown and original binding");
  // Genuine per-player attempts: preserve an active same-source preparation,
  // cancel a different source, and permit retry after a terminal failed attempt.
  MediaPlayer pending=new MediaPlayer();source(pending,"/dev/fd/owned");((X.S9Y)preview).A00=pending;((X.S9Y)preview).A03=X.S9Y.State.PREPARING;pending.prepareAsync();
  InstagramMediaPreparationCompat.prepareVideoSource(preview,"/dev/fd/owned");check(preview.teardowns==1,"active same source was cancelled");
  InstagramMediaPreparationCompat.prepareVideoSource(preview,"/dev/fd/new");check(preview.teardowns==2&&pending.macapkPreparationState()==MediaPlayer.PreparationState.IDLE,"different source did not cancel per-player wait");
  android.provider.MediaStoreProvider.next=java.util.concurrent.CompletableFuture.failedFuture(new java.io.IOException("synthetic conversion failure"));MediaPlayer failed=new MediaPlayer();source(failed,"/dev/fd/owned");((X.S9Y)preview).A00=failed;((X.S9Y)preview).A03=X.S9Y.State.PREPARING;failed.prepareAsync();long stop=System.nanoTime()+1000000000L;while(failed.macapkPreparationState()==MediaPlayer.PreparationState.PREPARING&&System.nanoTime()<stop)Thread.sleep(2);
  check(failed.macapkPreparationState()==MediaPlayer.PreparationState.FAILED,"failed attempt did not become terminal");InstagramMediaPreparationCompat.prepareVideoSource(preview,"/dev/fd/owned");check(preview.teardowns==3,"same-file failed preparation could not retry");
  Signals ready=new Signals();ready.frame=true;((X.S9Y)preview).A00=ready;InstagramMediaPreparationCompat.onRootDraw(root);check(field(gallery,"panel")==null,"actual ready frame retained gallery spinner");
  picker.setVisibility(View.GONE);InstagramMediaPreparationCompat.onRootDraw(root);check(field(gallery,"root")==null,"hidden gallery retained status");
  if(args.length>0){String name="X.S9Y";byte[] raw;try(var jar=new java.util.jar.JarFile(args[0]);var in=jar.getInputStream(jar.getJarEntry("X/S9Y.class"))){raw=in.readAllBytes();}byte[] patched=ClassFileRewriter.maybeRewrite(raw.clone(),name).bytes;String marker="prepareVideoSource";check(new String(patched,java.nio.charset.StandardCharsets.ISO_8859_1).contains(marker),"actual public preview entry was not patched");class Verified extends ClassLoader{Verified(){super(GalleryContract.class.getClassLoader());}Class<?> define(){return defineClass(name,patched,0,patched.length);}}new Verified().define().getDeclaredMethods();raw[5]^=1;check(!new String(ClassFileRewriter.maybeRewrite(raw,name).bytes,java.nio.charset.StandardCharsets.ISO_8859_1).contains(marker),"changed preview fingerprint patched");}
  System.out.println("PASS gallery conversion/progress/error/retry, source-attempt cancellation, same-file recovery, shadowed fields and actual preview rewrite");
 }
}'''
})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("source","jdk-home","work-root"):p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--source-overlay",action="store_true");p.add_argument("--app-classes",type=Path);a=p.parse_args();a.work_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gallery-preparation-",dir=a.work_root) as temporary:
        root=Path(temporary);files=[]
        for name,code in SOURCES.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(code);files.append(path)
        cp=os.pathsep.join(str(a.source/"runtime/build/lib"/name)for name in("android-framework.jar","macapk-loader.jar"))
        if a.app_classes:cp+=os.pathsep+str(a.app_classes)
        if a.source_overlay:files.extend(a.source/"runtime/java"/name for name in("com/macapk/loader/InstagramMediaPreparationCompat.java","android/media/MediaPlayer.java","com/macapk/loader/ClassFileRewriter.java"))
        subprocess.run([str(a.jdk_home/"bin/javac"),"-cp",cp,"-d",str(root),*map(str,files)],check=True,timeout=30)
        args=[str(a.app_classes)]if a.app_classes else []
        subprocess.run([str(a.jdk_home/"bin/java"),"-Djava.awt.headless=true","-cp",str(root)+os.pathsep+cp,"fixture.GalleryContract",*args],check=True,timeout=8,env=dict(os.environ,MACAPK_LOG_LEVEL="99"))


if __name__=="__main__":main()

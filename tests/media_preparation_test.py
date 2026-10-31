#!/usr/bin/env python3
"""Headless preparation state and root-identity contract; no application starts."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

SOURCES={
"com/macapk/loader/CameraBridge.java":r'''package com.macapk.loader;
public final class CameraBridge {
 public static long copyLatestArgb(long session,int[] pixels,int[] dims){dims[0]=1;dims[1]=1;pixels[0]=0xff00ff00;return 1234567;}
 public static long copyLatestRgba(long session,java.nio.ByteBuffer pixels,int[] dims){dims[0]=1;dims[1]=1;return 1234567;}
}''',
"fixture/Manager.java":r'''package fixture; public class Manager {
 public final Store A0V=new Store();public Manager(){A0V.A01.add(new X.CXg());}
 public static class Store{public java.util.List<Object>A01=new java.util.ArrayList<>();}
 public static class Model{public java.util.List<Object>A0x=java.util.List.of(new Object());}
}''',
"X/CXg.java":r'''package X;public class CXg{public fixture.Manager.Model A05=new fixture.Manager.Model();}''',
"androidx/fragment/app/FragmentContainerView.java":r'''package androidx.fragment.app;public class FragmentContainerView{
 public FragmentContainerView(android.content.Context c,android.util.AttributeSet a,fixture.Manager m){}
}''',
"com/instagram/modal/TransparentModalActivity.java":r'''package com.instagram.modal;
import android.content.pm.*;public class TransparentModalActivity extends android.app.Activity{
 public int backs;public final fixture.Manager manager=new fixture.Manager();
 final android.content.res.Resources resources=new android.content.res.Resources(new android.content.res.AssetManager(),new android.util.DisplayMetrics(),android.content.res.Configuration.macapkPhoneDefaults());
 public TransparentModalActivity() throws java.io.IOException{setIntent(new android.content.Intent().putExtra("fragment_name","clips_camera"));}
 public fixture.Manager renamedManager(){return manager;}
 public String getPackageName(){return "com.instagram.android";}
 public android.content.res.Resources getResources(){return resources;}
 public android.content.res.AssetManager getAssets(){return resources.getAssets();}
 public android.content.res.Resources.Theme getTheme(){return resources.newTheme();}
 public void onBackPressed(){backs++;}
 public PackageManager getPackageManager(){return new PackageManager(){
  public PackageInfo getPackageInfo(String n,int f){PackageInfo p=new PackageInfo();p.versionName="445.0.0.45.83";return p;}
  public ApplicationInfo getApplicationInfo(String n,int f){return new ApplicationInfo();}
  public java.util.List<ResolveInfo>queryIntentActivities(android.content.Intent i,int f){return java.util.List.of();}
  public int checkPermission(String p,String n){return PERMISSION_DENIED;}public boolean hasSystemFeature(String n){return false;}
  public String getInstallerPackageName(String n){return null;}
  public ServiceInfo getServiceInfo(android.content.ComponentName c,int f){return null;}
  public ProviderInfo getProviderInfo(android.content.ComponentName c,int f){return null;}
 };}
}''',
"fixture/PreparationContract.java":r'''package fixture;
import android.view.*;import android.widget.*;import com.macapk.loader.*;import com.instagram.modal.TransparentModalActivity;
public class PreparationContract{
 static Object field(String name)throws Exception{var f=InstagramMediaPreparationCompat.class.getDeclaredField(name);f.setAccessible(true);return f.get(null);}
 static int state()throws Exception{return (Integer)field("state");}
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 static void top(android.app.Activity a)throws Exception{var f=ActivityHost.class.getDeclaredField("stack");f.setAccessible(true);var q=(java.util.Deque<android.app.Activity>)f.get(null);q.clear();q.push(a);}
 static ViewGroup root(TransparentModalActivity a){ViewGroup r=(ViewGroup)a.getWindow().getDecorView();r.layout(0,0,786,1702);r.macapkDispatchAttachedToWindow();return r;}
 public static void main(String[]args)throws Exception{
  java.util.concurrent.atomic.AtomicReference<Throwable> coldError=new java.util.concurrent.atomic.AtomicReference<>();
  Thread cold=new Thread(()->{try{new android.graphics.SurfaceTexture(false).release();}catch(Throwable error){coldError.set(error);}},"cold-synthetic-texture");cold.start();cold.join(2000);
  check(!cold.isAlive()&&coldError.get()==null,"background cold texture constructor failed");
  android.os.Looper.prepareMainLooper();TransparentModalActivity a=new TransparentModalActivity();top(a);ViewGroup ar=root(a);int originalChildren=ar.getChildCount();
  InstagramMediaPreparationCompat.onRootDraw(new FrameLayout(a));check(state()==0,"unrelated root selected");
  InstagramMediaPreparationCompat.onRootDraw(ar);check(state()==1,"waiting state missing");
  check(field("statusPanel")==null&&ar.getChildCount()==originalChildren,"unobserved native preview was covered");
  Button next=new Button(a);next.setText("Next");java.util.concurrent.atomic.AtomicInteger nextClicks=new java.util.concurrent.atomic.AtomicInteger();next.setOnClickListener(v->nextClicks.incrementAndGet());
  ar.addView(next,new FrameLayout.LayoutParams(80,80));next.layout(706,0,786,80);
  for(int i=0;i<20;i++)InstagramMediaPreparationCompat.onRootDraw(ar);
  ar.dispatchTouchEvent(android.view.MotionEvent.obtain(1,1,0,746,40,0));ar.dispatchTouchEvent(android.view.MotionEvent.obtain(1,2,1,746,40,0));
  check(nextClicks.get()==1,"native editor Next was intercepted without Java frame hints");
  InstagramMediaPreparationCompat.reportFramePresented(ar);check(state()==1,"camera swap falsely marked ready");
  InstagramMediaPreparationCompat.reportFailure(new FrameLayout(a),"offscreen");check(state()==1,"offscreen error changed state");
  InstagramMediaPreparationCompat.reportFailure(ar,"renderer-internal-detail");check(state()==2,"known error missing");
  InstagramMediaPreparationCompat.reportFramePresented(ar);check(state()==2,"generic swap erased known renderer failure");
  LinearLayout panel=(LinearLayout)field("statusPanel");check(panel.getChildAt(1) instanceof Button,"error recovery control missing");
  check(panel.getAccessibilityLiveRegion()==View.ACCESSIBILITY_LIVE_REGION_POLITE,"error accessibility live region missing");
  check(!((TextView)panel.getChildAt(0)).getText().toString().contains("renderer-internal-detail"),"internal error details exposed");
  panel.getChildAt(1).performClick();check(a.backs==1&&state()==0,"Back recovery did not clear status");
  TransparentModalActivity b=new TransparentModalActivity();top(b);ViewGroup br=root(b);InstagramMediaPreparationCompat.onRootDraw(br);check(state()==1,"new editor did not wait");
  InstagramMediaPreparationCompat.reportFramePresented(ar);InstagramMediaPreparationCompat.reportFailure(ar,"old root");InstagramMediaPreparationCompat.onRootDetached(ar);
  check(state()==1&&field("editorRoot")==br,"old-root event or timeout changed new editor");
  check(state()==1&&field("statusPanel")==null,"missing native frame hints created a false error");
  TextureView preview=new TextureView(b);br.addView(preview);preview.layout(0,0,4,4);
  var texture=new android.graphics.SurfaceTexture(false);preview.setSurfaceTexture(texture);
  var bitmap=android.graphics.Bitmap.createBitmap(4,4,android.graphics.Bitmap.Config.ARGB_8888);
  var canvas=new android.graphics.Canvas(bitmap);
  preview.draw(canvas);check(state()==1,"empty texture falsely marked ready");
  texture.macapkQueueProducerFrame(new int[]{0xffff0000},1,1,1,null,null,false);
  texture.macapkLatchBitmap();texture.macapkAttachCameraSource(1,1,1);
  InstagramMediaPreparationCompat.reportSelectedFrame(preview,texture);check(state()==1,"camera texture falsely marked ready");
  texture.macapkDetachCameraSource();
  texture.macapkQueueProducerFrame(new int[]{0xffff0000},1,1,1,null,null,false);
  preview.draw(canvas);check(state()==3&&field("statusPanel")==null,"real selected texture frame did not confirm readiness");
  check(!InstagramMediaPreparationCompat.wantsSelectedFrameHint(),"ready preview kept reflection hot path enabled");
  InstagramMediaPreparationCompat.onRootDetached(br);check(state()==0&&field("editorRoot")==null,"detach did not release state");
  TransparentModalActivity c=new TransparentModalActivity();top(c);ViewGroup cr=root(c);InstagramMediaPreparationCompat.onRootDraw(cr);
  check(!InstagramMediaPreparationCompat.reportFramePresented(cr)&&state()==1,"native camera swap granted readiness");
  texture.macapkQueueProducerFrame(new int[]{0xffff0000},1,1,1,null,null,false);texture.macapkLatchBitmap();
  check(!InstagramMediaPreparationCompat.reportFramePresented(cr)&&state()==1,"old-root decoded frame granted readiness");
  var camera=new android.graphics.SurfaceTexture(false);camera.macapkAttachCameraSource(1,1,1);camera.macapkQueueFrame(1234567,null,0);check(camera.macapkLatchBitmap()!=null,"synthetic camera frame did not latch");
  check(!InstagramMediaPreparationCompat.reportFramePresented(cr)&&state()==1,"real camera latch granted readiness");
  var decoded=new android.graphics.SurfaceTexture(false);decoded.macapkQueueProducerFrame(new int[]{0xffff0000},1,1,1,null,null,true);check(decoded.macapkLatchBitmap()!=null,"premultiplied producer did not latch");
  check(!InstagramMediaPreparationCompat.reportFramePresented(cr)&&state()==1,"GL producer latch granted readiness");
  decoded.macapkQueueProducerFrame(new int[]{0xff0000ff},1,1,1,null,null,false);check(decoded.macapkLatchBitmap()!=null,"decoded file frame did not latch");
  check(state()==1,"file latch alone granted native presentation");
  check(InstagramMediaPreparationCompat.reportFramePresented(cr)&&state()==3,"decoded file latch plus native swap did not grant readiness");
  check(field("statusPanel")==null,"ready native preview retained waiting UI");
  InstagramMediaPreparationCompat.onRootDetached(cr);camera.release();decoded.release();texture.release();bitmap.recycle();
  TransparentModalActivity linearActivity=new TransparentModalActivity();top(linearActivity);
  LinearLayout linearDecor=new LinearLayout(linearActivity);linearDecor.setOrientation(LinearLayout.VERTICAL);
  FrameLayout content=new FrameLayout(linearActivity);content.setId(android.R.id.content);
  content.addView(new View(linearActivity),new FrameLayout.LayoutParams(-1,-1));
  linearDecor.addView(content,new LinearLayout.LayoutParams(-1,-1));
  var decorField=linearActivity.getWindow().getClass().getDeclaredField("decor");decorField.setAccessible(true);decorField.set(linearActivity.getWindow(),linearDecor);linearDecor.macapkDispatchAttachedToWindow();
  int widthSpec=View.MeasureSpec.makeMeasureSpec(786,View.MeasureSpec.EXACTLY),heightSpec=View.MeasureSpec.makeMeasureSpec(1702,View.MeasureSpec.EXACTLY);
  linearDecor.measure(widthSpec,heightSpec);linearDecor.layout(0,0,786,1702);
  InstagramMediaPreparationCompat.onRootDraw(linearDecor);
  linearDecor.measure(widthSpec,heightSpec);linearDecor.layout(0,0,786,1702);
  check(field("statusPanel")==null&&content.getChildCount()==1,"vertical native editor was covered");
  InstagramMediaPreparationCompat.reportFailure(linearDecor,"synthetic");
  linearDecor.measure(widthSpec,heightSpec);linearDecor.layout(0,0,786,1702);
  LinearLayout linearPanel=(LinearLayout)field("statusPanel");check(linearPanel.getHeight()>0,"vertical decor hides failure controls");
  linearPanel.getChildAt(1).performClick();check(linearActivity.backs==1&&state()==0,"vertical decor Back failed");
  System.out.println("PASS native editor controls without Java hints, genuine frame readiness, known errors, old-root isolation and Back recovery");
 }
}'''
}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True,type=Path);p.add_argument("--jdk-home",required=True,type=Path);p.add_argument("--work-root",required=True,type=Path)
    p.add_argument("--source-overlay",action="store_true");a=p.parse_args();a.work_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="preparation-contract-",dir=a.work_root)as temporary:
        root=Path(temporary);files=[]
        for name,code in SOURCES.items():
            f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(code);files.append(str(f))
        cp=os.pathsep.join(str(a.source/"runtime/build/lib"/n)for n in("android-framework.jar","macapk-loader.jar"))
        if a.source_overlay:
            files.extend(str(a.source/"runtime/java"/name)for name in("com/macapk/loader/InstagramMediaPreparationCompat.java","android/view/TextureView.java","android/graphics/SurfaceTexture.java"))
        subprocess.run([str(a.jdk_home/"bin/javac"),"-cp",cp,"-d",str(root),*files],check=True,timeout=30)
        subprocess.run([str(a.jdk_home/"bin/java"),"-Djava.awt.headless=true","-cp",str(root)+os.pathsep+cp,"fixture.PreparationContract"],check=True,timeout=15,env=dict(os.environ,MACAPK_LOG_LEVEL="99"))


if __name__=="__main__":main()

#!/usr/bin/env python3
"""Real public CcF setup must finish before late surface callbacks run."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

JAVA=r'''package fixture;
import android.view.*;import android.os.*;import java.lang.reflect.*;import java.util.concurrent.atomic.AtomicInteger;
public class CallbackOrderContract{
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 static void set(Class<?>c,Object o,String n,Object value)throws Exception{var f=c.getDeclaredField(n);f.setAccessible(true);f.set(o,value);}
 static SurfaceView view()throws Exception{
  var f=sun.misc.Unsafe.class.getDeclaredField("theUnsafe");f.setAccessible(true);var u=(sun.misc.Unsafe)f.get(null);SurfaceView view=(SurfaceView)u.allocateInstance(SurfaceView.class);
  Class<?> type=Class.forName("android.view.SurfaceView$SurfaceHolderImpl");var ctor=type.getDeclaredConstructor(SurfaceView.class);ctor.setAccessible(true);Object holder=ctor.newInstance(view);
  set(SurfaceView.class,view,"holder",holder);set(SurfaceView.class,view,"holderSurfaceCreatedFired",true);set(View.class,view,"macapkAttached",true);set(View.class,view,"visibility",View.VISIBLE);set(View.class,view,"right",774);set(View.class,view,"bottom",1376);
  ((SurfaceHolder)holder).setFixedSize(774,1376);return view;
 }
 static void drain()throws Exception{var method=MessageQueue.class.getDeclaredMethod("macapkPollDue");method.setAccessible(true);for(int i=0;i<100;i++){Message message=(Message)method.invoke(Looper.getMainLooper().getQueue());if(message==null)break;message.getTarget().dispatchMessage(message);}Handler.drainGlobal();}
 static class Callback implements SurfaceHolder.Callback{int created,changed,destroyed;public void surfaceCreated(SurfaceHolder h){created++;}public void surfaceChanged(SurfaceHolder h,int f,int w,int e){changed++;}public void surfaceDestroyed(SurfaceHolder h){destroyed++;}}
 static class EqualCallback extends Callback{public boolean equals(Object value){return value instanceof EqualCallback;}public int hashCode(){return 1;}}
 public static void main(String[]args)throws Exception{
  Looper.prepareMainLooper();SurfaceView view=view();Class<?> containerClass=Class.forName("X.CcF"),listenerClass=Class.forName("X.Owx");
  Object container=containerClass.getConstructor(SurfaceView.class).newInstance(view);AtomicInteger ready=new AtomicInteger();
  Object consumer=Proxy.newProxyInstance(listenerClass.getClassLoader(),new Class<?>[]{listenerClass},(o,m,a)->{if(m.getName().equals("G3D"))ready.incrementAndGet();if(m.getName().equals("hashCode"))return System.identityHashCode(o);if(m.getName().equals("equals"))return o==a[0];return null;});
  containerClass.getMethod("A09",listenerClass).invoke(container,consumer);drain();check(ready.get()==1,"actual CcF consumer missed the initial surface handoff: "+ready.get());
  SurfaceView removed=view();Callback cancelled=new Callback();removed.getHolder().addCallback(cancelled);check(cancelled.created==0,"late callback ran inline during setup");removed.getHolder().removeCallback(cancelled);drain();check(cancelled.created==0,"removed callback ran later");
  SurfaceView rebound=view();Callback cb=new Callback();rebound.getHolder().addCallback(cb);rebound.getHolder().removeCallback(cb);rebound.getHolder().addCallback(cb);drain();check(cb.created==1&&cb.changed==1,"remove/re-add replayed stale registration");
  SurfaceView equalRemoved=view();EqualCallback equivalent=new EqualCallback();equalRemoved.getHolder().addCallback(equivalent);equalRemoved.getHolder().removeCallback(new EqualCallback());drain();check(equivalent.created==0,"equal removal left stale registration");
  SurfaceView destroyed=view();Callback stale=new Callback();destroyed.getHolder().addCallback(stale);var destroy=destroyed.getHolder().getClass().getDeclaredMethod("fireDestroyed");destroy.setAccessible(true);destroy.invoke(destroyed.getHolder());drain();check(stale.created==0,"destroyed surface delivered stale create");
  SurfaceView nativeActivity=view();Callback async=new Callback();Thread registration=new Thread(()->nativeActivity.getHolder().addCallback(async),"synthetic-native-lifecycle");registration.start();registration.join(500);check(!registration.isAlive()&&async.created==0,"callback registration blocked or ran inline");drain();check(async.created==1,"queued callback did not reach owner loop");
  System.out.println("PASS actual CcF handoff and deferred callback removal/generation/nonblocking registration");
 }
}'''

def main():
 p=argparse.ArgumentParser();p.add_argument("--source",required=True,type=Path);p.add_argument("--jdk-home",required=True,type=Path);p.add_argument("--work-root",required=True,type=Path);p.add_argument("--app-classes",required=True,type=Path);p.add_argument("--source-overlay",action="store_true");a=p.parse_args();a.work_root.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix="surface-order-",dir=a.work_root)as temporary:
  root=Path(temporary);java=root/"CallbackOrderContract.java";java.write_text(JAVA)
  cp=os.pathsep.join([str(a.source/"runtime/build/lib"/n)for n in("android-framework.jar","macapk-loader.jar")]+[str(a.app_classes)])
  files=[str(java)]
  if a.source_overlay:files.append(str(a.source/"runtime/java/android/view/SurfaceView.java"))
  subprocess.run([str(a.jdk_home/"bin/javac"),"-cp",cp,"-d",str(root),*files],check=True,timeout=30)
  subprocess.run([str(a.jdk_home/"bin/java"),"-cp",str(root)+os.pathsep+cp,"fixture.CallbackOrderContract"],env=dict(os.environ,MACAPK_LOG_LEVEL="99",MACAPK_SDK_INT="33"),check=True,timeout=15)

if __name__=="__main__":main()

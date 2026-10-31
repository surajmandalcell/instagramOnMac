#!/usr/bin/env python3
"""SurfaceControl surfaces retain their producer and view ownership."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

JAVA = r'''package fixture;
import android.view.*;import java.lang.reflect.*;import java.util.concurrent.atomic.AtomicReference;
public class SurfaceControlContract {
 static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 static Object blank(Class<?> type)throws Exception{var f=sun.misc.Unsafe.class.getDeclaredField("theUnsafe");f.setAccessible(true);return ((sun.misc.Unsafe)f.get(null)).allocateInstance(type);}
 static void field(Class<?> type,Object instance,String name,Object value)throws Exception{var f=type.getDeclaredField(name);f.setAccessible(true);f.set(instance,value);}
 static class Stop extends RuntimeException{}
 public static void main(String[] args)throws Exception{
  new Surface().macapkNoteNativeWindowConsumer();check(SurfaceView.macapkNativeWindowLayerZ()==0,"legacy null changed initial policy");
  SurfaceView view=(SurfaceView)blank(SurfaceView.class);field(View.class,view,"macapkAttached",true);
  var hc=Class.forName("android.view.SurfaceView$SurfaceHolderImpl").getDeclaredConstructor(SurfaceView.class);hc.setAccessible(true);SurfaceHolder holder=(SurfaceHolder)hc.newInstance(view);field(SurfaceView.class,view,"holder",holder);
  SurfaceControl control=view.getSurfaceControl();Surface first=new Surface(control),second=new Surface(control);
  check(first.macapkGetOwnerSurfaceView()==view,"lost SurfaceView producer owner");first.release();check(second.isValid()&&holder.getSurface().isValid(),"release closed another handle");
  SurfaceControl child=new SurfaceControl.Builder().setParent(control).setBufferSize(320,240).build();Surface childSurface=new Surface(child);check(childSurface.macapkGetOwnerSurfaceView()==view,"child lost parent owner");
  Class<?> factory=Class.forName("X.1rR");Object factoryInstance=blank(factory);var create=factory.getDeclaredMethod("A01");create.setAccessible(true);SurfaceControl standalone=(SurfaceControl)create.invoke(factoryInstance);Surface standaloneSurface=new Surface(standalone);check(standaloneSurface.macapkGetOwnerSurfaceView()==null,"standalone had an owner");
  standaloneSurface.macapkNoteNativeWindowConsumer();SurfaceControl.Transaction transaction=new SurfaceControl.Transaction().reparent(standalone,control);check(standaloneSurface.macapkGetOwnerSurfaceView()==null,"reparent applied before transaction");transaction.apply();check(standaloneSurface.macapkGetOwnerSurfaceView()==view,"actual factory producer did not acquire parent owner");
  var nativeOwner=SurfaceView.class.getDeclaredField("sNativeWindowOwner");nativeOwner.setAccessible(true);check(((java.lang.ref.WeakReference<?>)nativeOwner.get(null)).get()==view,"previous native consumer missed reparent");
  new SurfaceControl.Transaction().reparent(standalone,null).apply();check(standaloneSurface.macapkGetOwnerSurfaceView()==null,"detached producer retained stale owner");
  check(SurfaceView.macapkNativeWindowLayerZ()==-1,"visible old owner remained published after detach");
  SurfaceView other=(SurfaceView)blank(SurfaceView.class);field(View.class,other,"macapkAttached",true);SurfaceControl otherRoot=new SurfaceControl.Builder().setLocalOwnerView(other).build();SurfaceControl newer=new SurfaceControl.Builder().setParent(otherRoot).build();new Surface(newer).macapkNoteNativeWindowConsumer();check(SurfaceView.macapkNativeWindowLayerZ()==1,"new owner was not visible");
  new SurfaceControl.Transaction().reparent(standalone,null).apply();standalone.release();check(SurfaceView.macapkNativeWindowLayerZ()==1&&((java.lang.ref.WeakReference<?>)nativeOwner.get(null)).get()==other,"old control hid newer owner");
  Surface lateSurface=new Surface(newer);SurfaceControl.Transaction lateReparent=new SurfaceControl.Transaction().reparent(newer,control);newer.release();check(SurfaceView.macapkNativeWindowLayerZ()==-1,"current control release did not hide layer");lateSurface.macapkNoteNativeWindowConsumer();lateReparent.apply();check(SurfaceView.macapkNativeWindowLayerZ()==-1,"late consumer or transaction revived released control");
  var legacy=SurfaceView.class.getDeclaredMethod("macapkNoteNativeWindowOwner",SurfaceView.class);legacy.setAccessible(true);legacy.invoke(null,view);newer.release();check(SurfaceView.macapkNativeWindowLayerZ()==1,"old control cleared legacy owner");legacy.invoke(null,new Object[]{null});check(SurfaceView.macapkNativeWindowLayerZ()==1,"legacy null changed policy");
  control.release();check(second.isValid(),"control release invalidated retained surface");try{new Surface(control);throw new AssertionError("released control accepted");}catch(IllegalArgumentException expected){}
  try{new Surface((SurfaceControl)null);throw new AssertionError("null accepted");}catch(IllegalArgumentException expected){}
  Class<?> listener=Class.forName("X.1rU"),base=listener.getSuperclass(),options=Class.forName("X.1Xb"),sink=Class.forName("X.nuJ");Object callback=blank(listener);
  field(base,callback,"A02",options.getConstructor().newInstance());field(listener,callback,"A01",child);AtomicReference<Surface> supplied=new AtomicReference<>();
  Object consumer=Proxy.newProxyInstance(sink.getClassLoader(),new Class<?>[]{sink},(o,m,a)->{if(m.getName().equals("setSurface")){supplied.set((Surface)a[0]);throw new Stop();}return null;});field(listener,callback,"A0C",consumer);
  try{listener.getMethod("surfaceCreated",SurfaceHolder.class).invoke(callback,holder);throw new AssertionError("sink not reached");}catch(InvocationTargetException e){if(!(e.getCause() instanceof Stop))throw e;}
  check(supplied.get()!=null&&supplied.get().isValid()&&supplied.get().macapkGetOwnerSurfaceView()==view,"actual X.1rU lost producer");
  System.out.println("PASS actual X.1rU surface handoff, owner inheritance and independent release");
 }
}'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);p.add_argument('--jdk-home',required=True,type=Path);p.add_argument('--work-root',required=True,type=Path);p.add_argument('--app-classes',required=True,type=Path);p.add_argument('--source-overlay',action='store_true');a=p.parse_args();a.work_root.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='surface-control-',dir=a.work_root) as temporary:
  root=Path(temporary);fixture=root/'SurfaceControlContract.java';fixture.write_text(JAVA);cp=os.pathsep.join([str(a.source/'runtime/build/lib'/n) for n in ('android-framework.jar','macapk-loader.jar')]+[str(a.app_classes)])
  files=[str(fixture)]
  if a.source_overlay:files += [str(a.source/'runtime/java/android/view'/n) for n in ('Surface.java','SurfaceControl.java','SurfaceView.java')]
  subprocess.run([str(a.jdk_home/'bin/javac'),'-cp',cp,'-d',str(root),*files],check=True,timeout=30)
  subprocess.run([str(a.jdk_home/'bin/java'),'-cp',str(root)+os.pathsep+cp,'fixture.SurfaceControlContract'],env=dict(os.environ,MACAPK_LOG_LEVEL='99',MACAPK_SDK_INT='33'),check=True,timeout=15)

if __name__=='__main__':main()

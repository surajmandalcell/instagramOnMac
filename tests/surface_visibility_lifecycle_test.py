#!/usr/bin/env python3
"""Hidden surfaces must not consume the real app's one-time renderer handoff."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

NATIVE = r'''#include <jni.h>
extern "C" JNIEXPORT jint JNICALL Java_com_macapk_loader_NativeCocoa_phoneWidth(JNIEnv*,jclass){return 774;}
extern "C" JNIEXPORT jint JNICALL Java_com_macapk_loader_NativeCocoa_phoneHeight(JNIEnv*,jclass){return 1376;}
extern "C" JNIEXPORT jlong JNICALL Java_com_macapk_loader_NativeCocoa_getOrCreateSharedMetalSurfaceView(JNIEnv*,jclass,jint,jint){return 0;}
extern "C" JNIEXPORT jlong JNICALL Java_com_macapk_loader_NativeCocoa_createMetalSurfaceViewForGl(JNIEnv*,jclass,jint,jint){return 0;}
'''

JAVA = r'''package fixture;
import android.view.*;import android.widget.*;import android.os.*;import java.lang.reflect.*;import java.util.concurrent.atomic.AtomicInteger;
public class VisibilityContract {
 static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 static void converge(SurfaceView view)throws Exception{try{SurfaceView.class.getMethod("macapkConvergeViewSurfaceLifecycle").invoke(view);}catch(NoSuchMethodException old){var m=SurfaceView.class.getDeclaredMethod("macapkConvergeSurfaceLifecycle",int.class,int.class);m.setAccessible(true);m.invoke(view,774,1376);}}
 static int drain()throws Exception{var poll=MessageQueue.class.getDeclaredMethod("macapkPollDue");poll.setAccessible(true);int count=0;for(int i=0;i<100;i++){Message m=(Message)poll.invoke(Looper.getMainLooper().getQueue());if(m==null)break;count++;m.getTarget().dispatchMessage(m);}Handler.drainGlobal();return count;}
 static class Events implements SurfaceHolder.Callback {int created,changed,destroyed;public void surfaceCreated(SurfaceHolder h){created++;}public void surfaceChanged(SurfaceHolder h,int f,int w,int t){changed++;}public void surfaceDestroyed(SurfaceHolder h){destroyed++;}}
 public static void main(String[] args)throws Exception{
  System.load(args[0]);Looper.prepareMainLooper();android.app.Activity context=new android.app.Activity();FrameLayout root=new FrameLayout(context);SurfaceView view=new SurfaceView(context);
  root.addView(view,new FrameLayout.LayoutParams(774,1376));root.layout(0,0,774,1376);view.layout(0,0,774,1376);view.setVisibility(View.INVISIBLE);root.macapkDispatchAttachedToWindow();
  Class<?> containerType=Class.forName("X.CcF"),listenerType=Class.forName("X.Owx");Object container=containerType.getConstructor(SurfaceView.class).newInstance(view);Events events=new Events();view.getHolder().addCallback(events);
  converge(view);drain();check(events.created==0,"hidden surface consumed initial creation before consumer setup");
  AtomicInteger ready=new AtomicInteger(),destroyed=new AtomicInteger();Object consumer=Proxy.newProxyInstance(listenerType.getClassLoader(),new Class<?>[]{listenerType},(o,m,a)->{switch(m.getName()){case "G3D":ready.incrementAndGet();break;case "G3I":destroyed.incrementAndGet();break;case "hashCode":return System.identityHashCode(o);case "equals":return o==a[0];}return null;});
  containerType.getMethod("A09",listenerType).invoke(container,consumer);drain();check(ready.get()==0,"hidden late registration received a surface");
  view.setVisibility(View.VISIBLE);converge(view);check(ready.get()==0,"visible handoff ran inline before owner turn");drain();check(ready.get()==1&&events.created==1,"actual CcF late consumer missed visible creation");
  converge(view);drain();check(ready.get()==1&&events.created==1,"stable traversal duplicated creation");
  view.setVisibility(View.INVISIBLE);converge(view);drain();check(events.destroyed==1&&destroyed.get()==1,"hide did not destroy exactly once");
  converge(view);drain();check(events.destroyed==1,"hidden traversal repeated destruction");
  view.setVisibility(View.VISIBLE);converge(view);drain();check(ready.get()==2&&events.created==2,"show did not create a fresh surface generation");
  root.setVisibility(View.INVISIBLE);converge(view);drain();check(events.destroyed==2,"hidden ancestor retained child surface");root.setVisibility(View.VISIBLE);converge(view);drain();check(ready.get()==3,"visible ancestor did not restore child surface");
  root.macapkDispatchDetachedFromWindow();converge(view);drain();check(events.destroyed==3,"detach did not destroy surface");
  root.macapkDispatchAttachedToWindow();converge(view);drain();check(ready.get()==4,"reattach did not create a new generation");
  view.setVisibility(View.INVISIBLE);converge(view);drain();view.setVisibility(View.VISIBLE);converge(view);view.setVisibility(View.INVISIBLE);converge(view);drain();check(ready.get()==4,"stale queued visible generation survived hide");
  for(int i=0;i<500;i++)converge(view);check(drain()<=4,"hidden traversals grew unbounded owner queue");
  view.setVisibility(View.VISIBLE);converge(view);drain();check(ready.get()==5,"show after stale queue failed");int previousDestroyed=events.destroyed;
  view.setVisibility(View.INVISIBLE);converge(view);view.setVisibility(View.VISIBLE);converge(view);drain();check(ready.get()==6&&events.destroyed==previousDestroyed+1,"rapid hide/show lost fresh surface generation");
  Thread worker=new Thread(()->{try{converge(view);}catch(Exception e){throw new RuntimeException(e);}},"synthetic-renderer");worker.start();worker.join(500);check(!worker.isAlive(),"lifecycle convergence blocked worker");drain();
  System.out.println("PASS actual CcF hidden setup, late consumer, visible generation, hide/ancestor/detach reset, stale queue and nonblocking convergence");
 }
}'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("source", "jdk-home", "work-root", "app-classes"):
        parser.add_argument("--" + flag, required=True, type=Path)
    parser.add_argument("--source-overlay", action="store_true")
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="surface-visibility-", dir=args.work_root) as temporary:
        root = Path(temporary)
        native = root / "cocoa_stub.cpp"
        native.write_text(NATIVE)
        library = root / "cocoa_stub.dylib"
        subprocess.run(["clang++", "-dynamiclib", "-I" + str(args.jdk_home / "include"), "-I" + str(args.jdk_home / "include/darwin"), str(native), "-o", str(library)], check=True, timeout=30)
        java = root / "VisibilityContract.java"
        java.write_text(JAVA)
        cp = os.pathsep.join([str(args.source / "runtime/build/lib" / name) for name in ("android-framework.jar", "macapk-loader.jar")] + [str(args.app_classes)])
        files = [str(java)]
        if args.source_overlay:
            files.append(str(args.source / "runtime/java/android/view/SurfaceView.java"))
        subprocess.run([str(args.jdk_home / "bin/javac"), "-cp", cp, "-d", str(root), *files], check=True, timeout=45)
        subprocess.run([str(args.jdk_home / "bin/java"), "-cp", str(root) + os.pathsep + cp, "fixture.VisibilityContract", str(library)], env=dict(os.environ, MACAPK_LOG_LEVEL="99", MACAPK_SDK_INT="33", MACAPK_SV_AOSP_ORDER="0"), check=True, timeout=20)


if __name__ == "__main__":
    main()

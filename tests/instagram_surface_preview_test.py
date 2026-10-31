#!/usr/bin/env python3
"""Actual CcF late registration must hand its ready surface to a new renderer.

HC4 is a fixture recorder. This checks event delivery, not native rendering.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
from surface_visibility_lifecycle_test import NATIVE

HC4 = r'''package X;
public final class HC4 implements Owx {
 public Object A09,A08,A0A;public int received;public android.view.Surface surface;public boolean initializationReady=true;
 public void G3D(android.view.Surface s,int w,int h){if(!initializationReady)return;received++;surface=s;A09=new Object();}
 public void G38(int w,int h){}public void G3I(){}public void G3f(){}
}'''

JAVA = r'''package fixture;
import android.view.*;import android.os.*;import java.lang.reflect.*;import java.util.*;
import com.macapk.loader.ClassFileRewriter;
public class LatePreviewContract {
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 static Object field(Object o,String n)throws Exception{var f=o.getClass().getField(n);return f.get(o);}
 static class App extends ClassLoader {
  final java.util.jar.JarFile jar;final boolean rewrite;
  App(String path,boolean adapt)throws Exception{super(LatePreviewContract.class.getClassLoader());jar=new java.util.jar.JarFile(path);rewrite=adapt;}
  protected Class<?> loadClass(String name,boolean resolve)throws ClassNotFoundException{
   if(!Set.of("X.CcF","X.CcH","X.LPu").contains(name))return super.loadClass(name,resolve);
   synchronized(getClassLoadingLock(name)){Class<?> found=findLoadedClass(name);if(found==null)try(var in=jar.getInputStream(jar.getJarEntry(name.replace('.','/')+".class"))){byte[] raw=in.readAllBytes();byte[] bytes=rewrite?ClassFileRewriter.maybeRewrite(raw,name).bytes:raw;found=defineClass(name,bytes,0,bytes.length);}catch(Exception e){throw new ClassNotFoundException(name,e);}if(resolve)resolveClass(found);return found;}
  }
 }
 static int drain()throws Exception{var p=MessageQueue.class.getDeclaredMethod("macapkPollDue");p.setAccessible(true);int count=0;for(int i=0;i<100;i++){Message m=(Message)p.invoke(Looper.getMainLooper().getQueue());if(m==null)break;count++;m.getTarget().dispatchMessage(m);}Handler.drainGlobal();return count;}
 static SurfaceView view(){SurfaceView v=new SurfaceView(new android.app.Activity());v.layout(0,0,774,1376);v.macapkDispatchAttachedToWindow();return v;}
 static void converge(SurfaceView v)throws Exception{SurfaceView.class.getMethod("macapkConvergeViewSurfaceLifecycle").invoke(v);drain();}
 static Object adapter(Class<?> c,SurfaceView v)throws Exception{return c.getConstructor(SurfaceView.class).newInstance(v);}
 static void join(Class<?> c,Object a,X.HC4 consumer)throws Exception{c.getMethod("A09",Class.forName("X.Owx")).invoke(a,consumer);}
 public static void main(String[]args)throws Exception{
  System.load(args[0]);Looper.prepareMainLooper();App app=new App(args[1],!Boolean.getBoolean("fixture.unpatched"));
  byte[] raw=app.jar.getInputStream(app.jar.getJarEntry("X/CcF.class")).readAllBytes(),changed=Arrays.copyOf(raw,raw.length+1);String hook="com/macapk/loader/InstagramSurfacePreviewCompat";
  check(!new String(ClassFileRewriter.maybeRewrite(changed,"X.CcF").bytes,java.nio.charset.StandardCharsets.ISO_8859_1).contains(hook),"changed fingerprint received preview hook");check(!new String(ClassFileRewriter.maybeRewrite(raw,"X.Unrelated").bytes,java.nio.charset.StandardCharsets.ISO_8859_1).contains(hook),"unrelated class received preview hook");
  Class<?> c=app.loadClass("X.CcF");
  SurfaceView v=view();Object a=adapter(c,v);converge(v);drain();
  X.HC4 late=new X.HC4();join(c,a,late);check(late.received==0,"late registration invoked renderer inline");drain();check(late.received==1&&late.surface==v.getHolder().getSurface(),"actual CcF late ready renderer missed surface");
  join(c,a,late);drain();check(late.received==1,"duplicate registration replayed surface");
  X.HC4 removed=new X.HC4();join(c,a,removed);((Set<?>)field(field(a,"A0D"),"A00")).remove(removed);drain();check(removed.received==0,"removed consumer received stale handoff");
  X.HC4 initialized=new X.HC4();initialized.A08=new Object();join(c,a,initialized);drain();check(initialized.received==0,"initialized renderer was recreated");
  X.HC4 hidden=new X.HC4();v.setVisibility(View.INVISIBLE);join(c,a,hidden);drain();check(hidden.received==0,"hidden renderer received handoff");
  SurfaceView pending=view();Object before=adapter(c,pending);X.HC4 normal=new X.HC4();join(c,before,normal);converge(pending);check(normal.received==1,"normal pending callback handoff count="+normal.received);
  SurfaceView existing=view();existing.getHolder().addCallback(new SurfaceHolder.Callback(){public void surfaceCreated(SurfaceHolder h){}public void surfaceChanged(SurfaceHolder h,int f,int w,int t){}public void surfaceDestroyed(SurfaceHolder h){}});converge(existing);Object queued=adapter(c,existing);X.HC4 queuedNormal=new X.HC4();join(c,queued,queuedNormal);drain();check(queuedNormal.received==1,"already queued holder callback duplicated handoff="+queuedNormal.received);
  SurfaceView earlyView=view();earlyView.setVisibility(View.INVISIBLE);Object early=adapter(c,earlyView);X.HC4 retry=new X.HC4();retry.initializationReady=false;join(c,early,retry);drain();check(retry.received==0,"early registration initialized without visible surface");
  earlyView.setVisibility(View.VISIBLE);converge(earlyView);check(retry.received==0&&retry.A09==null,"fixture did not preserve first uninitialized handoff");
  retry.initializationReady=true;for(int i=0;i<100;i++)join(c,early,retry);check(retry.received==0,"repeat ensure ran inline");int jobs=drain();check(retry.received==1,"same registered renderer never retried after initial unready handoff");check(jobs<=4,"repeated ensure grew pending owner jobs");join(c,early,retry);drain();check(retry.received==1,"initialized renderer received repeated retry");
  app.jar.close();System.out.println("PASS actual CcF late and repeated registration, bounded owner jobs, exactly once, removal, hidden and existing/pending renderer guards");
 }
}'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("source", "jdk-home", "work-root", "app-classes"):
        parser.add_argument("--" + flag, required=True, type=Path)
    parser.add_argument("--source-overlay", action="store_true")
    parser.add_argument("--unpatched", action="store_true")
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="instagram-preview-", dir=args.work_root) as temporary:
        root = Path(temporary)
        native = root / "cocoa_stub.cpp"
        native.write_text(NATIVE)
        library = root / "cocoa_stub.dylib"
        subprocess.run(["clang++", "-dynamiclib", "-I" + str(args.jdk_home / "include"), "-I" + str(args.jdk_home / "include/darwin"), str(native), "-o", str(library)], check=True, timeout=30)
        java = root / "LatePreviewContract.java"
        java.write_text(JAVA)
        shadow = root / "HC4.java"
        shadow.write_text(HC4)
        cp = os.pathsep.join([str(args.source / "runtime/build/lib" / name) for name in ("android-framework.jar", "macapk-loader.jar")] + [str(args.app_classes)])
        files = [str(java), str(shadow)]
        if args.source_overlay:
            files += [str(args.source / "runtime/java/com/macapk/loader" / name) for name in ("ClassFileRewriter.java", "InstagramSurfacePreviewCompat.java")]
        subprocess.run([str(args.jdk_home / "bin/javac"), "-cp", cp, "-d", str(root), *files], check=True, timeout=45)
        subprocess.run([str(args.jdk_home / "bin/java"), "-Dfixture.unpatched=" + str(args.unpatched).lower(), "-cp", str(root) + os.pathsep + cp, "fixture.LatePreviewContract", str(library), str(args.app_classes)], env=dict(os.environ, MACAPK_LOG_LEVEL="99", MACAPK_SDK_INT="33", MACAPK_SV_AOSP_ORDER="0"), check=True, timeout=20)


if __name__ == "__main__":
    main()

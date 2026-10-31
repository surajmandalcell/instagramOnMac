#!/usr/bin/env python3
"""View animation work must wait for owner frames instead of flooding its queue."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

JAVA = r'''package fixture;
import android.view.*;import android.os.*;import java.util.concurrent.atomic.AtomicInteger;
public class ViewAnimationContract {
 static void check(boolean b,String message){if(!b)throw new AssertionError(message);}
 static void drain()throws Exception{var poll=MessageQueue.class.getDeclaredMethod("macapkPollDue");poll.setAccessible(true);for(int i=0;i<100;i++){Message m=(Message)poll.invoke(Looper.getMainLooper().getQueue());if(m==null)break;m.getTarget().dispatchMessage(m);}Handler.drainGlobal();}
 static View attached(){View view=new View(new android.app.Activity());view.layout(0,0,100,100);view.macapkDispatchAttachedToWindow();return view;}
 static void frame(){Choreographer.macapkDriveMainFrame();}
 public static void main(String[]args)throws Exception{
  Looper.prepareMainLooper();Choreographer.getInstance();View view=attached();
  if(args.length>0){AtomicInteger canceled=new AtomicInteger();Runnable action=canceled::incrementAndGet;view.postOnAnimationDelayed(action,40);view.removeCallbacks(action);Thread.sleep(80);drain();check(canceled.get()==0,"fallback Handler animation was not canceled");System.out.println("PASS fallback animation cancellation");return;}
  AtomicInteger count=new AtomicInteger();Runnable ticker=new Runnable(){public void run(){if(count.incrementAndGet()<4)view.postOnAnimation(this);}};
  view.postOnAnimation(ticker);drain();check(count.get()==0,"animation ran in plain owner queue before a frame");
  frame();check(count.get()==1,"first frame did not run exactly one ticker");drain();check(count.get()==1,"self-post escaped frame queue");
  frame();check(count.get()==2,"self-post did not wait for next frame");view.removeCallbacks(ticker);frame();check(count.get()==2,"removeCallbacks failed to cancel self-post");
  AtomicInteger delayed=new AtomicInteger();view.postOnAnimationDelayed(delayed::incrementAndGet,60);frame();check(delayed.get()==0,"delayed animation ran before its deadline");Thread.sleep(75);drain();check(delayed.get()==0,"delayed animation ran outside a frame");frame();check(delayed.get()==1,"due delayed animation missed next frame");
  AtomicInteger canceled=new AtomicInteger();Runnable action=canceled::incrementAndGet;view.post(action);view.postOnAnimation(action);view.postOnAnimationDelayed(action,1);check(view.removeCallbacks(action),"removeCallbacks return contract changed");Thread.sleep(3);drain();frame();check(canceled.get()==0,"removeCallbacks did not cancel Handler and animation paths");
  AtomicInteger plain=new AtomicInteger();view.post(plain::incrementAndGet);drain();check(plain.get()==1,"ordinary View.post incorrectly became frame-bound");
  View detached=new View(new android.app.Activity());AtomicInteger pending=new AtomicInteger();Runnable removed=pending::incrementAndGet;detached.postOnAnimation(removed);detached.removeCallbacks(removed);detached.postOnAnimation(pending::incrementAndGet);drain();frame();check(pending.get()==0,"detached animation ran before attachment");detached.macapkDispatchAttachedToWindow();drain();check(pending.get()==0,"attach executed animation before next frame");frame();check(pending.get()==1,"detached queue lost action or replayed canceled action");
  AtomicInteger worker=new AtomicInteger();Thread owner=Thread.currentThread();Thread producer=new Thread(()->view.postOnAnimation(()->{check(Thread.currentThread()==owner,"animation ran on posting worker");worker.incrementAndGet();}),"synthetic-animation-producer");producer.start();producer.join(500);check(!producer.isAlive(),"worker animation post blocked");drain();check(worker.get()==0,"worker animation ran without a frame");frame();check(worker.get()==1,"worker used an undriven Choreographer");
  System.out.println("PASS frame-bound View animation, next-frame self-post, delay, cancellation, detached queue and worker-to-owner delivery");
 }
}'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("source", "jdk-home", "work-root"):
        parser.add_argument("--" + flag, required=True, type=Path)
    parser.add_argument("--source-overlay", action="store_true")
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="view-animation-", dir=args.work_root) as temporary:
        root = Path(temporary)
        java = root / "ViewAnimationContract.java"
        java.write_text(JAVA)
        cp = os.pathsep.join(str(args.source / "runtime/build/lib" / name) for name in ("android-framework.jar", "macapk-loader.jar"))
        files = [str(java)]
        if args.source_overlay:
            files += [str(args.source / "runtime/java/android/view" / name) for name in ("View.java", "Choreographer.java")]
        subprocess.run([str(args.jdk_home / "bin/javac"), "-cp", cp, "-d", str(root), *files], check=True, timeout=45)
        subprocess.run([str(args.jdk_home / "bin/java"), "-cp", str(root) + os.pathsep + cp, "fixture.ViewAnimationContract"], env=dict(os.environ, MACAPK_LOG_LEVEL="99", MACAPK_REAL_LOOPER="1"), check=True, timeout=15)
        subprocess.run([str(args.jdk_home / "bin/java"), "-cp", str(root) + os.pathsep + cp, "fixture.ViewAnimationContract", "fallback"], env=dict(os.environ, MACAPK_LOG_LEVEL="99", MACAPK_REAL_LOOPER="0", MACAPK_CHOREO_VSYNC_THREADS="0"), check=True, timeout=15)


if __name__ == "__main__":
    main()

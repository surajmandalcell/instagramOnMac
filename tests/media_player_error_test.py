#!/usr/bin/env python3
"""Check Android asynchronous player error/completion ordering without native I/O."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

JAVA=r'''package fixture;
import android.media.MediaPlayer;import android.os.*;import java.util.*;import java.util.concurrent.*;import java.util.concurrent.atomic.*;
public class PlayerErrorContract {
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 public static void main(String[] args)throws Exception{
  AtomicReference<Throwable> error=new AtomicReference<>();CountDownLatch done=new CountDownLatch(1);
  Thread owner=new Thread(()->{try{Looper.prepare();Looper loop=Looper.myLooper();Handler handler=new Handler(loop);
   List<String> events=new ArrayList<>();int[] stage={0};Runnable[] next=new Runnable[1];
   next[0]=()->{int current=stage[0]++;if(current==4){loop.quit();done.countDown();return;}
    MediaPlayer player=new MediaPlayer(){public void prepare(){}};
    player.setOnCompletionListener(p->{try{check(Thread.currentThread().getName().equals("player-error-owner"),"wrong callback owner");events.add("complete");check(current<2,"handled/reset error invoked completion");}catch(Throwable t){error.set(t);}});
    if(current>0)player.setOnErrorListener((p,w,x)->{events.add("error");if(current==3)p.reset();return current==2;});
    player.prepareAsync();handler.postDelayed(()->{try{List<String> expected=current==0?List.of("complete"):current==1?List.of("error","complete"):List.of("error");check(events.equals(expected),"error callback sequence stage"+current+": "+events);events.clear();player.release();next[0].run();}catch(Throwable t){error.set(t);loop.quit();done.countDown();}},150);
   };next[0].run();Looper.loop();
  }catch(Throwable t){error.set(t);done.countDown();}},"player-error-owner");owner.setDaemon(true);owner.start();check(done.await(4,TimeUnit.SECONDS),"error callback deadline");if(error.get()!=null)throw new AssertionError(error.get());
  System.out.println("PASS absent/false listener completes; handled/reset error does not; owner-looper ordering");
 }
}'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("source","jdk-home","work-root"):p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--source-overlay",action="store_true");a=p.parse_args();a.work_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="player-error-",dir=a.work_root) as temporary:
        root=Path(temporary);test=root/"PlayerErrorContract.java";test.write_text(JAVA)
        cp=os.pathsep.join(str(a.source/"runtime/build/lib"/n)for n in("android-framework.jar","macapk-loader.jar"));files=[test]
        if a.source_overlay:files.append(a.source/"runtime/java/android/media/MediaPlayer.java")
        subprocess.run([str(a.jdk_home/"bin/javac"),"-cp",cp,"-d",str(root),*map(str,files)],check=True,timeout=30)
        subprocess.run([str(a.jdk_home/"bin/java"),"-cp",str(root)+os.pathsep+cp,"fixture.PlayerErrorContract"],check=True,timeout=6,env=dict(os.environ,MACAPK_LOG_LEVEL="99"))


if __name__=="__main__":main()

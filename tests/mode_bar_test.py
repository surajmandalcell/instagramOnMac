#!/usr/bin/env python3
"""Compact creation modes must not cover the gallery. No app or GUI starts."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

JAVA = r'''package com.macapk.loader;
import android.view.*;import android.widget.*;
public class ModeBarContract {
 static int spec(int n,int m){return View.MeasureSpec.makeMeasureSpec(n,m);}
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 public static void main(String[]args){
  for(int width:new int[]{645,786})for(int parentMode:new int[]{View.MeasureSpec.EXACTLY,View.MeasureSpec.AT_MOST,View.MeasureSpec.UNSPECIFIED}){
   FrameLayout selector=new FrameLayout(null){public android.content.res.Resources getResources(){return android.content.res.Resources.getSystem();}};selector.setPadding(6,8,6,8);
   TextView[] originals=new TextView[4];int[] calls=new int[4];
   for(int i=0;i<4;i++){final int index=i;originals[i]=new TextView(null);originals[i].setOnClickListener(v->calls[index]++);selector.addView(originals[i],new FrameLayout.LayoutParams(100,34));}
   originals[2].setSelected(true);
   var bar=InstagramModeBarCompat.install(selector,originals);
   int compact=Math.max(1,Math.round(48*selector.getResources().getDisplayMetrics().density));
   var lp=(FrameLayout.LayoutParams)bar.getLayoutParams();
   check(lp.height==compact && (lp.gravity&Gravity.VERTICAL_GRAVITY_MASK)==Gravity.BOTTOM,"bar must have compact bottom layout parameters");
   check(InstagramModeBarCompat.install(selector,originals)==bar&&selector.getChildCount()==5,"duplicate installation");
   selector.measure(spec(width,View.MeasureSpec.EXACTLY),spec(1702,parentMode));selector.layout(0,0,width,selector.getMeasuredHeight());
   check(bar.getHeight()==compact,"full viewport covered");
   if(parentMode!=View.MeasureSpec.EXACTLY)check(selector.getMeasuredHeight()==compact+16,"wrap-content selector grew to viewport");
   check(bar.getBottom()==selector.getHeight()-8,"bar must stay at bottom");
   for(int i=0;i<4;i++){check(bar.buttons[i].getLeft()==bar.getWidth()*i/4&&bar.buttons[i].getRight()==bar.getWidth()*(i+1)/4,"mode clipped");bar.buttons[i].performClick();check(calls[i]==1,"original mode callback lost");}
   bar.measure(spec(width,View.MeasureSpec.EXACTLY),spec(32,View.MeasureSpec.EXACTLY));check(bar.getMeasuredHeight()==32,"short exact host ignored");
  }
  System.out.println("PASS full-height, wrap-content, unspecified and short selectors; all four original mode callbacks");
 }
}'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ("source", "jdk-home", "work-root"):
        p.add_argument("--"+flag, required=True, type=Path)
    p.add_argument("--source-overlay", action="store_true")
    a=p.parse_args();a.work_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mode-bar-",dir=a.work_root) as temporary:
        root=Path(temporary);fixture=root/"ModeBarContract.java";fixture.write_text(JAVA)
        cp=os.pathsep.join(str(a.source/"runtime/build/lib"/name) for name in ("android-framework.jar","macapk-loader.jar"))
        files=[str(fixture)]
        if a.source_overlay:files.append(str(a.source/"runtime/java/com/macapk/loader/InstagramModeBarCompat.java"))
        subprocess.run([str(a.jdk_home/"bin/javac"),"-cp",cp,"-d",str(root),*files],check=True,timeout=30)
        subprocess.run([str(a.jdk_home/"bin/java"),"-Djava.awt.headless=true","-cp",str(root)+os.pathsep+cp,"com.macapk.loader.ModeBarContract"],check=True,timeout=15,env=dict(os.environ,MACAPK_LOG_LEVEL="99"))


if __name__=="__main__":main()

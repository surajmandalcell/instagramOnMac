"""Check Browse-only gallery layout, click routing, indices, and folder raster."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

JAVA = r'''
package com.macapk.loader;
import android.graphics.*;
import android.view.*;
import android.widget.*;
public final class GalleryBrowseContract {
 static int exact(int n){return View.MeasureSpec.makeMeasureSpec(n,View.MeasureSpec.EXACTLY);}
 static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 static void tap(View view,float x,float y){view.dispatchTouchEvent(MotionEvent.obtain(0,0,0,x,y,0));view.dispatchTouchEvent(MotionEvent.obtain(0,1,1,x,y,0));}
 public static void main(String[] args)throws Exception{
  var resources=new android.content.res.Resources(null,null,null);
  android.content.Context context=new android.content.Context(){
   public String getPackageName(){return "org.macapk.synthetic.gallery";}
   public android.content.res.Resources getResources(){return resources;}
   public android.content.res.AssetManager getAssets(){return null;}
   public android.content.Context getApplicationContext(){return this;}
   public ClassLoader getClassLoader(){return getClass().getClassLoader();}
   public java.io.File getFilesDir(){return null;}public java.io.File getCacheDir(){return null;}
   public java.io.File getDir(String name,int mode){return null;}
  };
  for(float density:new float[]{1f,1.5f,2f,3f})for(int width:new int[]{155,160,192,300}){
   resources.getDisplayMetrics().density=density;
   var gallery=new FrameLayout(context);var slot=new FrameLayout(context);
   var mediaOne=new View(context);var mediaTwo=new View(context);
   gallery.addView(slot);gallery.addView(mediaOne);gallery.addView(mediaTwo);
   var image=new ImageView(context);image.setImageDrawable(new android.graphics.drawable.ColorDrawable(0xff262a30));
   slot.addView(image,new FrameLayout.LayoutParams(-1,-1));
   int[] clicked={0,0,0};slot.setTag(0);
   slot.setOnClickListener(view->{if(((Integer)view.getTag())==0)clicked[0]++;else clicked[2]=(Integer)view.getTag();});
   slot.setContentDescription("Camera");image.setContentDescription("Camera");
   var tile=InstagramGalleryCompat.install(slot,image,()->clicked[1]++);
   check(tile!=null&&tile.getChildCount()==1,"gallery must have one Browse action");
   check("Browse Mac files".contentEquals(tile.browse.getContentDescription()),"Browse label missing");
   slot.measure(exact(width),exact(width));slot.layout(0,0,width,width);
   check(tile.browse.getWidth()==width&&tile.browse.getLeft()==0,"Browse does not fill existing slot");
   check(gallery.getChildCount()==3&&gallery.getChildAt(1)==mediaOne&&gallery.getChildAt(2)==mediaTwo,"media selection positions changed");
   check(slot.getContentDescription()==null&&image.getContentDescription()==null,"Camera remains an accessible option");
   slot.performClick();tap(slot,width*.2f,width*.5f);tap(slot,width*.8f,width*.5f);
   check(clicked[0]==0&&clicked[1]==3,"a gallery click still opens Camera or misses Browse");
   Bitmap raster=Bitmap.createBitmap(width,width,Bitmap.Config.ARGB_8888);slot.draw(new Canvas(raster));
   int minX=width,maxX=-1,minY=width,maxY=-1;
   float cy=width*.4f;
   for(int y=Math.max(0,(int)(cy-10*density));y<Math.min(width,(int)(cy+12*density));y++)for(int x=0;x<width;x++){
    int color=raster.getPixel(x,y);if((color&255)>200&&((color>>>8)&255)>200&&((color>>>16)&255)>200){minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);}
   }
   check(maxX-minX>(maxY-minY)*1.25,"folder icon is not a wide tabbed shape");
   if(width==160&&density==2f&&args.length>0)try(var out=new java.io.FileOutputStream(args[0])){check(raster.compress(Bitmap.CompressFormat.PNG,100,out),"raster export failed");}
   image.setImageDrawable(new android.graphics.drawable.ColorDrawable(0xff808080));slot.setTag(2);slot.draw(new Canvas(raster));slot.performClick();
   check(clicked[1]==3&&clicked[2]==2,"recycled media cell lost its original item index/click handler");
   check(tile.browse.getVisibility()==View.GONE,"Browse remains exposed on a recycled media item");raster.recycle();
  }
  System.out.println("PASS: Browse only; both cell halves route to Browse; folder raster; 4 sizes x 4 densities; original media indices and recycled clicks preserved");
 }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--jdk-home", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--preview", type=Path)
    options = parser.parse_args()
    options.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gallery-browse-", dir=options.work_root) as temporary:
        root = Path(temporary)
        (root / "GalleryBrowseContract.java").write_text(JAVA)
        classpath = os.pathsep.join(str(options.source / "runtime/build/lib" / name) for name in ("android-framework.jar", "macapk-loader.jar"))
        subprocess.run([str(options.jdk_home / "bin/javac"), "-cp", classpath, "-d", str(root),
                        str(options.source / "runtime/java/com/macapk/loader/InstagramGalleryCompat.java"), str(root / "GalleryBrowseContract.java")], check=True, timeout=40)
        subprocess.run([str(options.jdk_home / "bin/java"), "-Djava.awt.headless=true", "-cp", str(root)+os.pathsep+classpath,
                        "com.macapk.loader.GalleryBrowseContract", *([str(options.preview)] if options.preview else [])],
                       env=dict(os.environ, MACAPK_LOG_LEVEL="99"), check=True, timeout=30)


if __name__ == "__main__":
    main()

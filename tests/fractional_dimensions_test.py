#!/usr/bin/env python3
"""Fractional dimension sizing and offsets through real TypedArray and XML inflation."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

JAVA = r'''
import android.content.*;import android.content.res.*;import android.util.*;import android.view.*;import java.lang.reflect.*;import java.io.*;
public class DimensionContract{
 public static class Index{public String entryNameOf(int id){return "layout_height";}}
 static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 static AttributeSet attributes(String value){return(AttributeSet)Proxy.newProxyInstance(AttributeSet.class.getClassLoader(),new Class[]{AttributeSet.class},(p,m,a)->{
  switch(m.getName()){
   case "getAttributeCount":return 1;case "getAttributeName":return "layout_height";case "getAttributeNameResource":return android.R.attr.layout_height;
   case "getAttributeNamespace":return "http://schemas.android.com/apk/res/android";case "getAttributeValue":return value;
   case "getStyleAttribute":return 0;case "getPositionDescription":return "synthetic dimension";
   default:if(m.getReturnType()==boolean.class)return false;if(m.getReturnType()==int.class)return a!=null&&a.length>0&&a[a.length-1]instanceof Integer?a[a.length-1]:0;return null;
  }
 });}
 static Context context(Resources r){return new Context(){public String getPackageName(){return "org.macapk.synthetic.dimensions";}public Resources getResources(){return r;}public AssetManager getAssets(){return null;}public Context getApplicationContext(){return this;}public ClassLoader getClassLoader(){return getClass().getClassLoader();}public File getFilesDir(){return null;}public File getCacheDir(){return null;}public File getDir(String n,int mode){return null;}};}
 static View inflate(Context context,String xml)throws Exception{
  var factory=javax.xml.parsers.DocumentBuilderFactory.newInstance();factory.setNamespaceAware(true);
  var element=factory.newDocumentBuilder().parse(new org.xml.sax.InputSource(new StringReader(xml))).getDocumentElement();
  var method=LayoutInflater.class.getDeclaredMethod("inflateElement",org.w3c.dom.Element.class,ViewGroup.class);method.setAccessible(true);
  return(View)method.invoke(LayoutInflater.from(context),element,null);
 }
 public static void main(String[]args)throws Exception{
  Resources.macapkSetResourceIndex(new Index());Resources r=new Resources(null,null,null);r.getDisplayMetrics().density=2f;r.getDisplayMetrics().scaledDensity=2f;r.getDisplayMetrics().densityDpi=320;Context c=context(r);
  String[] values={"0.25dp","-0.25dp","0.75dp","-0.75dp","0dp","0px"};int[] sizes={1,-1,2,-2,0,0},offsets={0,0,1,-1,0,0};
  for(int i=0;i<values.length;i++){
   TypedArray array=new TypedArray(r,new int[]{android.R.attr.layout_height},attributes(values[i]));
   check(array.getDimensionPixelSize(0,99)==sizes[i],"TypedArray pixel size wrong: "+values[i]);
   check(array.getDimensionPixelOffset(0,99)==offsets[i],"TypedArray pixel offset must truncate: "+values[i]);array.recycle();
   View view=inflate(c,"<FrameLayout xmlns:android='http://schemas.android.com/apk/res/android' android:layout_width='wrap_content' android:layout_height='wrap_content'><View android:layout_width='"+values[i]+"' android:layout_height='"+values[i]+"'/></FrameLayout>");
   var lp=((ViewGroup)view).getChildAt(0).getLayoutParams();check(lp.width==sizes[i]&&lp.height==sizes[i],"XML layout dimensions wrong: "+values[i]);
  }
  TypedArray absent=new TypedArray(r,new int[]{android.R.attr.layout_height});check(absent.getDimensionPixelSize(0,37)==37&&absent.getDimensionPixelOffset(0,37)==37,"missing dimension changed default");
  for(int fallback:new int[]{16777217,-16777217,Integer.MAX_VALUE,Integer.MIN_VALUE})check(absent.getDimensionPixelOffset(0,fallback)==fallback,"missing pixel offset lost integer precision");
  for(String value:new String[]{"match_parent","fill_parent","-1","wrap_content","-2","0"}){
   ViewGroup group=(ViewGroup)inflate(c,"<FrameLayout xmlns:android='http://schemas.android.com/apk/res/android'><View android:layout_width='"+value+"' android:layout_height='"+value+"'/></FrameLayout>");
   int expected=value.equals("wrap_content")||value.equals("-2")?-2:value.equals("0")?0:-1;var lp=group.getChildAt(0).getLayoutParams();check(lp.width==expected&&lp.height==expected,"layout enum or zero changed: "+value);
  }
  if(args.length>0){
   ViewGroup root=(ViewGroup)inflate(c,"<androidx.constraintlayout.widget.ConstraintLayout xmlns:android='http://schemas.android.com/apk/res/android' android:layout_width='match_parent' android:layout_height='match_parent'><LinearLayout android:layout_width='match_parent' android:layout_height='wrap_content' android:orientation='vertical'><View android:layout_width='match_parent' android:layout_height='0.25dp'/></LinearLayout></androidx.constraintlayout.widget.ConstraintLayout>");
   check(root.getClass().getName().equals("androidx.constraintlayout.widget.ConstraintLayout"),"actual app ConstraintLayout was replaced");
   ViewGroup footer=(ViewGroup)root.getChildAt(0);check(footer.getChildAt(0).getLayoutParams().height==1,"actual app nested footer divider became match-constraint zero");
  }
  System.out.println("PASS fractional positive/negative dimensions, literal zero/enums and truncating offsets/defaults"+(args.length>0?"; actual app nested footer divider":""));
 }
}'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "jdk-home", "work-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--app-classes", type=Path)
    parser.add_argument("--source-overlay", action="store_true")
    parser.add_argument("--baseline-dir", type=Path, help="Compile the saved pre-fix TypedArray and LayoutInflater sources")
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dimensions-", dir=args.work_root) as directory:
        root = Path(directory); (root / "DimensionContract.java").write_text(JAVA)
        cp = os.pathsep.join(str(args.source / "runtime/build/lib" / name) for name in ("android-framework.jar", "macapk-loader.jar"))
        if args.app_classes:cp += os.pathsep + str(args.app_classes)
        files = [root / "DimensionContract.java"]
        if args.baseline_dir:
            for name in ("TypedArray", "LayoutInflater"):
                target = root / (name + ".java");target.write_text((args.baseline_dir / (name + ".pre28.java")).read_text());files.append(target)
        elif args.source_overlay:files.extend(args.source / "runtime/java" / name for name in ("android/content/res/TypedArray.java", "android/view/LayoutInflater.java"))
        subprocess.run([str(args.jdk_home / "bin/javac"), "-cp", cp, "-d", str(root), *map(str, files)], check=True, timeout=30)
        subprocess.run([str(args.jdk_home / "bin/java"), "-Djava.awt.headless=true", "-cp", str(root) + os.pathsep + cp, "DimensionContract", *(["app"] if args.app_classes else [])], check=True, timeout=20, env=dict(os.environ, MACAPK_LOG_LEVEL="99"))


if __name__ == "__main__":
    main()

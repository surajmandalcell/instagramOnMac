"""Compile and render external-camera shaders on the real ANGLE Metal backend."""
import argparse
from pathlib import Path
import subprocess
import tempfile

CPP = r'''
#include "external_texture_bridge.h"
#include <EGL/eglext.h>
#include <EGL/eglext_angle.h>
#include <GLES3/gl3.h>
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
using namespace macapk::external_texture;
void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
GLuint shader(GLenum type,const std::string& text,bool adapt){
 GLuint object=glCreateShader(type);
 if(adapt)SetShaderSource(object,text);else{const char*p=text.c_str();glShaderSource(object,1,&p,nullptr);}
 glCompileShader(object);GLint ok=0;glGetShaderiv(object,GL_COMPILE_STATUS,&ok);
 if(!ok){char error[2048];glGetShaderInfoLog(object,sizeof(error),nullptr,error);std::cerr<<error<<'\n';}
 check(ok,"shader did not compile");return object;
}
int main(){try{
 const std::string comment="/* samplerExternalOES\n#extension GL_OES_EGL_image_external : require\n*/\n// samplerExternalOES\nfloat samplerExternalOES_suffix;\n";
 check(ShaderSource(comment)==comment,"comments or longer identifiers changed");
 const std::string ordinary="precision mediump float;uniform sampler2D image;void main(){gl_FragColor=texture2D(image,vec2(0.5));}";
 check(ShaderSource(ordinary)==ordinary,"ordinary shader changed");
 check(Target(GL_TEXTURE_CUBE_MAP)==GL_TEXTURE_CUBE_MAP&&Binding(GL_MAX_TEXTURE_SIZE)==GL_MAX_TEXTURE_SIZE,"ordinary target changed");
 auto platform=(PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");check(platform,"platform entry absent");
 EGLint displayAttrs[]={EGL_PLATFORM_ANGLE_TYPE_ANGLE,EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE,EGL_NONE};
 EGLDisplay display=platform(EGL_PLATFORM_ANGLE_ANGLE,nullptr,displayAttrs);check(display!=EGL_NO_DISPLAY,"Metal display absent");
 check(eglInitialize(display,nullptr,nullptr),"EGL initialize failed");
 EGLint configAttrs[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE};
 EGLConfig config;EGLint count=0;check(eglChooseConfig(display,configAttrs,&config,1,&count)&&count==1,"pbuffer config absent");
 EGLint surfaceAttrs[]={EGL_WIDTH,8,EGL_HEIGHT,8,EGL_NONE};EGLSurface surface=eglCreatePbufferSurface(display,config,surfaceAttrs);check(surface!=EGL_NO_SURFACE,"pbuffer absent");
 for(int version:{2,3}){
  EGLint attrs[]={EGL_CONTEXT_CLIENT_VERSION,version,EGL_NONE};EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,attrs);check(context!=EGL_NO_CONTEXT,"context absent");
  check(eglMakeCurrent(display,surface,surface,context),"make current failed");
  std::string fragment=version==2?
   "#extension GL_OES_EGL_image_external : require\nprecision mediump float;uniform samplerExternalOES image;varying vec2 uv;void main(){gl_FragColor=texture2D(image,uv);}":
   "#version 300 es\n#extension GL_OES_EGL_image_external_essl3 : require\nprecision mediump float;uniform samplerExternalOES image;in vec2 uv;out vec4 color;void main(){color=texture(image,uv);}";
  std::string transformed=ShaderSource(fragment);
  check(std::count(fragment.begin(),fragment.end(),'\n')==std::count(transformed.begin(),transformed.end(),'\n'),"source line numbers changed");
  GLuint raw=glCreateShader(GL_FRAGMENT_SHADER);const char* original=fragment.c_str();glShaderSource(raw,1,&original,nullptr);glCompileShader(raw);GLint rawOk=0;glGetShaderiv(raw,GL_COMPILE_STATUS,&rawOk);glDeleteShader(raw);
  std::cout<<"Unadapted ES"<<version<<" shader status="<<rawOk<<'\n';
  GLuint fs=shader(GL_FRAGMENT_SHADER,fragment,true);std::string retained;check(OriginalSource(fs,retained)&&retained==fragment,"original source unavailable");
  GLuint vs=shader(GL_VERTEX_SHADER,version==2?
   "attribute vec2 position;attribute vec2 texcoord;varying vec2 uv;void main(){gl_Position=vec4(position,0.,1.);uv=texcoord;}":
   "#version 300 es\nin vec2 position;in vec2 texcoord;out vec2 uv;void main(){gl_Position=vec4(position,0.,1.);uv=texcoord;}",true);
  GLuint program=glCreateProgram();glAttachShader(program,vs);glAttachShader(program,fs);glLinkProgram(program);GLint linked=0;glGetProgramiv(program,GL_LINK_STATUS,&linked);check(linked,"program link failed");glUseProgram(program);
  GLuint texture;glGenTextures(1,&texture);BindTexture(0x8D65,texture);GLint bound=0;glGetIntegerv(Binding(0x8D67),&bound);check(bound==(GLint)texture,"external binding mismatch");
  GLint wrap=0;glGetTexParameteriv(Target(0x8D65),GL_TEXTURE_WRAP_S,&wrap);check(wrap==GL_CLAMP_TO_EDGE,"external default wrap wrong");
  glTexParameteri(Target(0x8D65),GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(Target(0x8D65),GL_TEXTURE_MAG_FILTER,GL_NEAREST);
  const unsigned char pixels[]={255,0,0,255,0,0,255,255,255,0,0,255,0,0,255,255};
  glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,2,2,0,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
  BindTexture(0x8D65,texture);GLint filter=0;glGetTexParameteriv(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,&filter);check(filter==GL_NEAREST,"rebind reset app filter");
  glUniform1i(glGetUniformLocation(program,"image"),0);
  const GLfloat vertices[]={-1,-1,0,0, 1,-1,1,0, -1,1,0,1, 1,1,1,1};
  GLuint vbo;glGenBuffers(1,&vbo);glBindBuffer(GL_ARRAY_BUFFER,vbo);glBufferData(GL_ARRAY_BUFFER,sizeof(vertices),vertices,GL_STATIC_DRAW);
  GLint pos=glGetAttribLocation(program,"position"),uv=glGetAttribLocation(program,"texcoord");glEnableVertexAttribArray(pos);glEnableVertexAttribArray(uv);
  glVertexAttribPointer(pos,2,GL_FLOAT,GL_FALSE,4*sizeof(GLfloat),nullptr);glVertexAttribPointer(uv,2,GL_FLOAT,GL_FALSE,4*sizeof(GLfloat),(void*)(2*sizeof(GLfloat)));
  glViewport(0,0,8,8);glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);glDrawArrays(GL_TRIANGLE_STRIP,0,4);
  unsigned char result[8*8*4];glReadPixels(0,0,8,8,GL_RGBA,GL_UNSIGNED_BYTE,result);check(glGetError()==GL_NO_ERROR,"render GL error");
  auto pixel=[&](int x,int y){return result+4*(y*8+x);};check(pixel(1,4)[0]>240&&pixel(1,4)[2]<15&&pixel(6,4)[2]>240&&pixel(6,4)[0]<15,"real texture pixels did not reach output");
  ForgetShader(fs);ForgetShader(vs);check(!OriginalSource(fs,retained),"deleted shader source retained");
  SetShaderSource(fs,fragment);ForgetContext(context);check(!OriginalSource(fs,retained),"destroyed context source retained");
  glDeleteProgram(program);glDeleteShader(fs);glDeleteShader(vs);glDeleteTextures(1,&texture);glDeleteBuffers(1,&vbo);
  eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);eglDestroyContext(display,context);
  std::cout<<"PASS ES"<<version<<" Metal external shader, binding, defaults, preserved source and real red/blue pixels\n";
 }
 eglDestroySurface(display,surface);eglTerminate(display);return 0;
}catch(const std::exception&error){std::cerr<<error.what()<<'\n';return 1;}}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=True)
    angle = args.source / "thirdparty/angle-prebuilt"
    with tempfile.TemporaryDirectory(prefix="external-texture-", dir=args.work_root) as temporary:
        root = Path(temporary)
        (root / "test.cpp").write_text(CPP)
        subprocess.run(["clang++", "-std=c++17", "-I" + str(args.source / "runtime/src"),
                        "-I" + str(angle / "include"), str(root / "test.cpp"), "-L" + str(angle / "lib"),
                        "-lEGL", "-lGLESv2", "-Wl,-rpath," + str(angle / "lib"), "-o", str(root / "test")], check=True, timeout=60)
        subprocess.run([str(root / "test")], cwd=angle / "lib", check=True, timeout=30)


if __name__ == "__main__":
    main()

/* gen.py が作る。手で直さない */
#define NREAL 368
static const char *real_names[NREAL] = {
    "GlmfBeginGlsBlock",
    "GlmfCloseMetaFile",
    "GlmfEndGlsBlock",
    "GlmfEndPlayback",
    "GlmfInitPlayback",
    "GlmfPlayGlsRecord",
    "glAccum",
    "glAlphaFunc",
    "glAreTexturesResident",
    "glArrayElement",
    "glBegin",
    "glBindTexture",
    "glBitmap",
    "glBlendFunc",
    "glCallList",
    "glCallLists",
    "glClear",
    "glClearAccum",
    "glClearColor",
    "glClearDepth",
    "glClearIndex",
    "glClearStencil",
    "glClipPlane",
    "glColor3b",
    "glColor3bv",
    "glColor3d",
    "glColor3dv",
    "glColor3f",
    "glColor3fv",
    "glColor3i",
    "glColor3iv",
    "glColor3s",
    "glColor3sv",
    "glColor3ub",
    "glColor3ubv",
    "glColor3ui",
    "glColor3uiv",
    "glColor3us",
    "glColor3usv",
    "glColor4b",
    "glColor4bv",
    "glColor4d",
    "glColor4dv",
    "glColor4f",
    "glColor4fv",
    "glColor4i",
    "glColor4iv",
    "glColor4s",
    "glColor4sv",
    "glColor4ub",
    "glColor4ubv",
    "glColor4ui",
    "glColor4uiv",
    "glColor4us",
    "glColor4usv",
    "glColorMask",
    "glColorMaterial",
    "glColorPointer",
    "glCopyPixels",
    "glCopyTexImage1D",
    "glCopyTexImage2D",
    "glCopyTexSubImage1D",
    "glCopyTexSubImage2D",
    "glCullFace",
    "glDebugEntry",
    "glDeleteLists",
    "glDeleteTextures",
    "glDepthFunc",
    "glDepthMask",
    "glDepthRange",
    "glDisable",
    "glDisableClientState",
    "glDrawArrays",
    "glDrawBuffer",
    "glDrawElements",
    "glDrawPixels",
    "glEdgeFlag",
    "glEdgeFlagPointer",
    "glEdgeFlagv",
    "glEnable",
    "glEnableClientState",
    "glEnd",
    "glEndList",
    "glEvalCoord1d",
    "glEvalCoord1dv",
    "glEvalCoord1f",
    "glEvalCoord1fv",
    "glEvalCoord2d",
    "glEvalCoord2dv",
    "glEvalCoord2f",
    "glEvalCoord2fv",
    "glEvalMesh1",
    "glEvalMesh2",
    "glEvalPoint1",
    "glEvalPoint2",
    "glFeedbackBuffer",
    "glFinish",
    "glFlush",
    "glFogf",
    "glFogfv",
    "glFogi",
    "glFogiv",
    "glFrontFace",
    "glFrustum",
    "glGenLists",
    "glGenTextures",
    "glGetBooleanv",
    "glGetClipPlane",
    "glGetDoublev",
    "glGetError",
    "glGetFloatv",
    "glGetIntegerv",
    "glGetLightfv",
    "glGetLightiv",
    "glGetMapdv",
    "glGetMapfv",
    "glGetMapiv",
    "glGetMaterialfv",
    "glGetMaterialiv",
    "glGetPixelMapfv",
    "glGetPixelMapuiv",
    "glGetPixelMapusv",
    "glGetPointerv",
    "glGetPolygonStipple",
    "glGetString",
    "glGetTexEnvfv",
    "glGetTexEnviv",
    "glGetTexGendv",
    "glGetTexGenfv",
    "glGetTexGeniv",
    "glGetTexImage",
    "glGetTexLevelParameterfv",
    "glGetTexLevelParameteriv",
    "glGetTexParameterfv",
    "glGetTexParameteriv",
    "glHint",
    "glIndexMask",
    "glIndexPointer",
    "glIndexd",
    "glIndexdv",
    "glIndexf",
    "glIndexfv",
    "glIndexi",
    "glIndexiv",
    "glIndexs",
    "glIndexsv",
    "glIndexub",
    "glIndexubv",
    "glInitNames",
    "glInterleavedArrays",
    "glIsEnabled",
    "glIsList",
    "glIsTexture",
    "glLightModelf",
    "glLightModelfv",
    "glLightModeli",
    "glLightModeliv",
    "glLightf",
    "glLightfv",
    "glLighti",
    "glLightiv",
    "glLineStipple",
    "glLineWidth",
    "glListBase",
    "glLoadIdentity",
    "glLoadMatrixd",
    "glLoadMatrixf",
    "glLoadName",
    "glLogicOp",
    "glMap1d",
    "glMap1f",
    "glMap2d",
    "glMap2f",
    "glMapGrid1d",
    "glMapGrid1f",
    "glMapGrid2d",
    "glMapGrid2f",
    "glMaterialf",
    "glMaterialfv",
    "glMateriali",
    "glMaterialiv",
    "glMatrixMode",
    "glMultMatrixd",
    "glMultMatrixf",
    "glNewList",
    "glNormal3b",
    "glNormal3bv",
    "glNormal3d",
    "glNormal3dv",
    "glNormal3f",
    "glNormal3fv",
    "glNormal3i",
    "glNormal3iv",
    "glNormal3s",
    "glNormal3sv",
    "glNormalPointer",
    "glOrtho",
    "glPassThrough",
    "glPixelMapfv",
    "glPixelMapuiv",
    "glPixelMapusv",
    "glPixelStoref",
    "glPixelStorei",
    "glPixelTransferf",
    "glPixelTransferi",
    "glPixelZoom",
    "glPointSize",
    "glPolygonMode",
    "glPolygonOffset",
    "glPolygonStipple",
    "glPopAttrib",
    "glPopClientAttrib",
    "glPopMatrix",
    "glPopName",
    "glPrioritizeTextures",
    "glPushAttrib",
    "glPushClientAttrib",
    "glPushMatrix",
    "glPushName",
    "glRasterPos2d",
    "glRasterPos2dv",
    "glRasterPos2f",
    "glRasterPos2fv",
    "glRasterPos2i",
    "glRasterPos2iv",
    "glRasterPos2s",
    "glRasterPos2sv",
    "glRasterPos3d",
    "glRasterPos3dv",
    "glRasterPos3f",
    "glRasterPos3fv",
    "glRasterPos3i",
    "glRasterPos3iv",
    "glRasterPos3s",
    "glRasterPos3sv",
    "glRasterPos4d",
    "glRasterPos4dv",
    "glRasterPos4f",
    "glRasterPos4fv",
    "glRasterPos4i",
    "glRasterPos4iv",
    "glRasterPos4s",
    "glRasterPos4sv",
    "glReadBuffer",
    "glReadPixels",
    "glRectd",
    "glRectdv",
    "glRectf",
    "glRectfv",
    "glRecti",
    "glRectiv",
    "glRects",
    "glRectsv",
    "glRenderMode",
    "glRotated",
    "glRotatef",
    "glScaled",
    "glScalef",
    "glScissor",
    "glSelectBuffer",
    "glShadeModel",
    "glStencilFunc",
    "glStencilMask",
    "glStencilOp",
    "glTexCoord1d",
    "glTexCoord1dv",
    "glTexCoord1f",
    "glTexCoord1fv",
    "glTexCoord1i",
    "glTexCoord1iv",
    "glTexCoord1s",
    "glTexCoord1sv",
    "glTexCoord2d",
    "glTexCoord2dv",
    "glTexCoord2f",
    "glTexCoord2fv",
    "glTexCoord2i",
    "glTexCoord2iv",
    "glTexCoord2s",
    "glTexCoord2sv",
    "glTexCoord3d",
    "glTexCoord3dv",
    "glTexCoord3f",
    "glTexCoord3fv",
    "glTexCoord3i",
    "glTexCoord3iv",
    "glTexCoord3s",
    "glTexCoord3sv",
    "glTexCoord4d",
    "glTexCoord4dv",
    "glTexCoord4f",
    "glTexCoord4fv",
    "glTexCoord4i",
    "glTexCoord4iv",
    "glTexCoord4s",
    "glTexCoord4sv",
    "glTexCoordPointer",
    "glTexEnvf",
    "glTexEnvfv",
    "glTexEnvi",
    "glTexEnviv",
    "glTexGend",
    "glTexGendv",
    "glTexGenf",
    "glTexGenfv",
    "glTexGeni",
    "glTexGeniv",
    "glTexImage1D",
    "glTexImage2D",
    "glTexParameterf",
    "glTexParameterfv",
    "glTexParameteri",
    "glTexParameteriv",
    "glTexSubImage1D",
    "glTexSubImage2D",
    "glTranslated",
    "glTranslatef",
    "glVertex2d",
    "glVertex2dv",
    "glVertex2f",
    "glVertex2fv",
    "glVertex2i",
    "glVertex2iv",
    "glVertex2s",
    "glVertex2sv",
    "glVertex3d",
    "glVertex3dv",
    "glVertex3f",
    "glVertex3fv",
    "glVertex3i",
    "glVertex3iv",
    "glVertex3s",
    "glVertex3sv",
    "glVertex4d",
    "glVertex4dv",
    "glVertex4f",
    "glVertex4fv",
    "glVertex4i",
    "glVertex4iv",
    "glVertex4s",
    "glVertex4sv",
    "glVertexPointer",
    "glViewport",
    "wglChoosePixelFormat",
    "wglCopyContext",
    "wglCreateContext",
    "wglCreateLayerContext",
    "wglDeleteContext",
    "wglDescribeLayerPlane",
    "wglDescribePixelFormat",
    "wglGetCurrentContext",
    "wglGetCurrentDC",
    "wglGetDefaultProcAddress",
    "wglGetLayerPaletteEntries",
    "wglGetPixelFormat",
    "wglGetProcAddress",
    "wglMakeCurrent",
    "wglRealizeLayerPalette",
    "wglSetLayerPaletteEntries",
    "wglSetPixelFormat",
    "wglShareLists",
    "wglSwapBuffers",
    "wglSwapLayerBuffers",
    "wglSwapMultipleBuffers",
    "wglUseFontBitmapsA",
    "wglUseFontBitmapsW",
    "wglUseFontOutlinesA",
    "wglUseFontOutlinesW",
};
#define IX_GlmfBeginGlsBlock 0
#define IX_GlmfCloseMetaFile 1
#define IX_GlmfEndGlsBlock 2
#define IX_GlmfEndPlayback 3
#define IX_GlmfInitPlayback 4
#define IX_GlmfPlayGlsRecord 5
#define IX_glAccum 6
#define IX_glAlphaFunc 7
#define IX_glAreTexturesResident 8
#define IX_glArrayElement 9
#define IX_glBegin 10
#define IX_glBindTexture 11
#define IX_glBitmap 12
#define IX_glBlendFunc 13
#define IX_glCallList 14
#define IX_glCallLists 15
#define IX_glClear 16
#define IX_glClearAccum 17
#define IX_glClearColor 18
#define IX_glClearDepth 19
#define IX_glClearIndex 20
#define IX_glClearStencil 21
#define IX_glClipPlane 22
#define IX_glColor3b 23
#define IX_glColor3bv 24
#define IX_glColor3d 25
#define IX_glColor3dv 26
#define IX_glColor3f 27
#define IX_glColor3fv 28
#define IX_glColor3i 29
#define IX_glColor3iv 30
#define IX_glColor3s 31
#define IX_glColor3sv 32
#define IX_glColor3ub 33
#define IX_glColor3ubv 34
#define IX_glColor3ui 35
#define IX_glColor3uiv 36
#define IX_glColor3us 37
#define IX_glColor3usv 38
#define IX_glColor4b 39
#define IX_glColor4bv 40
#define IX_glColor4d 41
#define IX_glColor4dv 42
#define IX_glColor4f 43
#define IX_glColor4fv 44
#define IX_glColor4i 45
#define IX_glColor4iv 46
#define IX_glColor4s 47
#define IX_glColor4sv 48
#define IX_glColor4ub 49
#define IX_glColor4ubv 50
#define IX_glColor4ui 51
#define IX_glColor4uiv 52
#define IX_glColor4us 53
#define IX_glColor4usv 54
#define IX_glColorMask 55
#define IX_glColorMaterial 56
#define IX_glColorPointer 57
#define IX_glCopyPixels 58
#define IX_glCopyTexImage1D 59
#define IX_glCopyTexImage2D 60
#define IX_glCopyTexSubImage1D 61
#define IX_glCopyTexSubImage2D 62
#define IX_glCullFace 63
#define IX_glDebugEntry 64
#define IX_glDeleteLists 65
#define IX_glDeleteTextures 66
#define IX_glDepthFunc 67
#define IX_glDepthMask 68
#define IX_glDepthRange 69
#define IX_glDisable 70
#define IX_glDisableClientState 71
#define IX_glDrawArrays 72
#define IX_glDrawBuffer 73
#define IX_glDrawElements 74
#define IX_glDrawPixels 75
#define IX_glEdgeFlag 76
#define IX_glEdgeFlagPointer 77
#define IX_glEdgeFlagv 78
#define IX_glEnable 79
#define IX_glEnableClientState 80
#define IX_glEnd 81
#define IX_glEndList 82
#define IX_glEvalCoord1d 83
#define IX_glEvalCoord1dv 84
#define IX_glEvalCoord1f 85
#define IX_glEvalCoord1fv 86
#define IX_glEvalCoord2d 87
#define IX_glEvalCoord2dv 88
#define IX_glEvalCoord2f 89
#define IX_glEvalCoord2fv 90
#define IX_glEvalMesh1 91
#define IX_glEvalMesh2 92
#define IX_glEvalPoint1 93
#define IX_glEvalPoint2 94
#define IX_glFeedbackBuffer 95
#define IX_glFinish 96
#define IX_glFlush 97
#define IX_glFogf 98
#define IX_glFogfv 99
#define IX_glFogi 100
#define IX_glFogiv 101
#define IX_glFrontFace 102
#define IX_glFrustum 103
#define IX_glGenLists 104
#define IX_glGenTextures 105
#define IX_glGetBooleanv 106
#define IX_glGetClipPlane 107
#define IX_glGetDoublev 108
#define IX_glGetError 109
#define IX_glGetFloatv 110
#define IX_glGetIntegerv 111
#define IX_glGetLightfv 112
#define IX_glGetLightiv 113
#define IX_glGetMapdv 114
#define IX_glGetMapfv 115
#define IX_glGetMapiv 116
#define IX_glGetMaterialfv 117
#define IX_glGetMaterialiv 118
#define IX_glGetPixelMapfv 119
#define IX_glGetPixelMapuiv 120
#define IX_glGetPixelMapusv 121
#define IX_glGetPointerv 122
#define IX_glGetPolygonStipple 123
#define IX_glGetString 124
#define IX_glGetTexEnvfv 125
#define IX_glGetTexEnviv 126
#define IX_glGetTexGendv 127
#define IX_glGetTexGenfv 128
#define IX_glGetTexGeniv 129
#define IX_glGetTexImage 130
#define IX_glGetTexLevelParameterfv 131
#define IX_glGetTexLevelParameteriv 132
#define IX_glGetTexParameterfv 133
#define IX_glGetTexParameteriv 134
#define IX_glHint 135
#define IX_glIndexMask 136
#define IX_glIndexPointer 137
#define IX_glIndexd 138
#define IX_glIndexdv 139
#define IX_glIndexf 140
#define IX_glIndexfv 141
#define IX_glIndexi 142
#define IX_glIndexiv 143
#define IX_glIndexs 144
#define IX_glIndexsv 145
#define IX_glIndexub 146
#define IX_glIndexubv 147
#define IX_glInitNames 148
#define IX_glInterleavedArrays 149
#define IX_glIsEnabled 150
#define IX_glIsList 151
#define IX_glIsTexture 152
#define IX_glLightModelf 153
#define IX_glLightModelfv 154
#define IX_glLightModeli 155
#define IX_glLightModeliv 156
#define IX_glLightf 157
#define IX_glLightfv 158
#define IX_glLighti 159
#define IX_glLightiv 160
#define IX_glLineStipple 161
#define IX_glLineWidth 162
#define IX_glListBase 163
#define IX_glLoadIdentity 164
#define IX_glLoadMatrixd 165
#define IX_glLoadMatrixf 166
#define IX_glLoadName 167
#define IX_glLogicOp 168
#define IX_glMap1d 169
#define IX_glMap1f 170
#define IX_glMap2d 171
#define IX_glMap2f 172
#define IX_glMapGrid1d 173
#define IX_glMapGrid1f 174
#define IX_glMapGrid2d 175
#define IX_glMapGrid2f 176
#define IX_glMaterialf 177
#define IX_glMaterialfv 178
#define IX_glMateriali 179
#define IX_glMaterialiv 180
#define IX_glMatrixMode 181
#define IX_glMultMatrixd 182
#define IX_glMultMatrixf 183
#define IX_glNewList 184
#define IX_glNormal3b 185
#define IX_glNormal3bv 186
#define IX_glNormal3d 187
#define IX_glNormal3dv 188
#define IX_glNormal3f 189
#define IX_glNormal3fv 190
#define IX_glNormal3i 191
#define IX_glNormal3iv 192
#define IX_glNormal3s 193
#define IX_glNormal3sv 194
#define IX_glNormalPointer 195
#define IX_glOrtho 196
#define IX_glPassThrough 197
#define IX_glPixelMapfv 198
#define IX_glPixelMapuiv 199
#define IX_glPixelMapusv 200
#define IX_glPixelStoref 201
#define IX_glPixelStorei 202
#define IX_glPixelTransferf 203
#define IX_glPixelTransferi 204
#define IX_glPixelZoom 205
#define IX_glPointSize 206
#define IX_glPolygonMode 207
#define IX_glPolygonOffset 208
#define IX_glPolygonStipple 209
#define IX_glPopAttrib 210
#define IX_glPopClientAttrib 211
#define IX_glPopMatrix 212
#define IX_glPopName 213
#define IX_glPrioritizeTextures 214
#define IX_glPushAttrib 215
#define IX_glPushClientAttrib 216
#define IX_glPushMatrix 217
#define IX_glPushName 218
#define IX_glRasterPos2d 219
#define IX_glRasterPos2dv 220
#define IX_glRasterPos2f 221
#define IX_glRasterPos2fv 222
#define IX_glRasterPos2i 223
#define IX_glRasterPos2iv 224
#define IX_glRasterPos2s 225
#define IX_glRasterPos2sv 226
#define IX_glRasterPos3d 227
#define IX_glRasterPos3dv 228
#define IX_glRasterPos3f 229
#define IX_glRasterPos3fv 230
#define IX_glRasterPos3i 231
#define IX_glRasterPos3iv 232
#define IX_glRasterPos3s 233
#define IX_glRasterPos3sv 234
#define IX_glRasterPos4d 235
#define IX_glRasterPos4dv 236
#define IX_glRasterPos4f 237
#define IX_glRasterPos4fv 238
#define IX_glRasterPos4i 239
#define IX_glRasterPos4iv 240
#define IX_glRasterPos4s 241
#define IX_glRasterPos4sv 242
#define IX_glReadBuffer 243
#define IX_glReadPixels 244
#define IX_glRectd 245
#define IX_glRectdv 246
#define IX_glRectf 247
#define IX_glRectfv 248
#define IX_glRecti 249
#define IX_glRectiv 250
#define IX_glRects 251
#define IX_glRectsv 252
#define IX_glRenderMode 253
#define IX_glRotated 254
#define IX_glRotatef 255
#define IX_glScaled 256
#define IX_glScalef 257
#define IX_glScissor 258
#define IX_glSelectBuffer 259
#define IX_glShadeModel 260
#define IX_glStencilFunc 261
#define IX_glStencilMask 262
#define IX_glStencilOp 263
#define IX_glTexCoord1d 264
#define IX_glTexCoord1dv 265
#define IX_glTexCoord1f 266
#define IX_glTexCoord1fv 267
#define IX_glTexCoord1i 268
#define IX_glTexCoord1iv 269
#define IX_glTexCoord1s 270
#define IX_glTexCoord1sv 271
#define IX_glTexCoord2d 272
#define IX_glTexCoord2dv 273
#define IX_glTexCoord2f 274
#define IX_glTexCoord2fv 275
#define IX_glTexCoord2i 276
#define IX_glTexCoord2iv 277
#define IX_glTexCoord2s 278
#define IX_glTexCoord2sv 279
#define IX_glTexCoord3d 280
#define IX_glTexCoord3dv 281
#define IX_glTexCoord3f 282
#define IX_glTexCoord3fv 283
#define IX_glTexCoord3i 284
#define IX_glTexCoord3iv 285
#define IX_glTexCoord3s 286
#define IX_glTexCoord3sv 287
#define IX_glTexCoord4d 288
#define IX_glTexCoord4dv 289
#define IX_glTexCoord4f 290
#define IX_glTexCoord4fv 291
#define IX_glTexCoord4i 292
#define IX_glTexCoord4iv 293
#define IX_glTexCoord4s 294
#define IX_glTexCoord4sv 295
#define IX_glTexCoordPointer 296
#define IX_glTexEnvf 297
#define IX_glTexEnvfv 298
#define IX_glTexEnvi 299
#define IX_glTexEnviv 300
#define IX_glTexGend 301
#define IX_glTexGendv 302
#define IX_glTexGenf 303
#define IX_glTexGenfv 304
#define IX_glTexGeni 305
#define IX_glTexGeniv 306
#define IX_glTexImage1D 307
#define IX_glTexImage2D 308
#define IX_glTexParameterf 309
#define IX_glTexParameterfv 310
#define IX_glTexParameteri 311
#define IX_glTexParameteriv 312
#define IX_glTexSubImage1D 313
#define IX_glTexSubImage2D 314
#define IX_glTranslated 315
#define IX_glTranslatef 316
#define IX_glVertex2d 317
#define IX_glVertex2dv 318
#define IX_glVertex2f 319
#define IX_glVertex2fv 320
#define IX_glVertex2i 321
#define IX_glVertex2iv 322
#define IX_glVertex2s 323
#define IX_glVertex2sv 324
#define IX_glVertex3d 325
#define IX_glVertex3dv 326
#define IX_glVertex3f 327
#define IX_glVertex3fv 328
#define IX_glVertex3i 329
#define IX_glVertex3iv 330
#define IX_glVertex3s 331
#define IX_glVertex3sv 332
#define IX_glVertex4d 333
#define IX_glVertex4dv 334
#define IX_glVertex4f 335
#define IX_glVertex4fv 336
#define IX_glVertex4i 337
#define IX_glVertex4iv 338
#define IX_glVertex4s 339
#define IX_glVertex4sv 340
#define IX_glVertexPointer 341
#define IX_glViewport 342
#define IX_wglChoosePixelFormat 343
#define IX_wglCopyContext 344
#define IX_wglCreateContext 345
#define IX_wglCreateLayerContext 346
#define IX_wglDeleteContext 347
#define IX_wglDescribeLayerPlane 348
#define IX_wglDescribePixelFormat 349
#define IX_wglGetCurrentContext 350
#define IX_wglGetCurrentDC 351
#define IX_wglGetDefaultProcAddress 352
#define IX_wglGetLayerPaletteEntries 353
#define IX_wglGetPixelFormat 354
#define IX_wglGetProcAddress 355
#define IX_wglMakeCurrent 356
#define IX_wglRealizeLayerPalette 357
#define IX_wglSetLayerPaletteEntries 358
#define IX_wglSetPixelFormat 359
#define IX_wglShareLists 360
#define IX_wglSwapBuffers 361
#define IX_wglSwapLayerBuffers 362
#define IX_wglSwapMultipleBuffers 363
#define IX_wglUseFontBitmapsA 364
#define IX_wglUseFontBitmapsW 365
#define IX_wglUseFontOutlinesA 366
#define IX_wglUseFontOutlinesW 367

// Hidden OpenGL compute context. The source shader mirrors DeckOrbitRenderer.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

class GpuDeckRenderer
{
    [StructLayout(LayoutKind.Sequential)]
    struct PixelFormat
    {
        public ushort Size, Version;
        public uint Flags;
        public byte Type, ColorBits, RedBits, RedShift, GreenBits, GreenShift, BlueBits, BlueShift,
            AlphaBits, AlphaShift;
        public byte AccumBits, AccumRed, AccumGreen, AccumBlue, AccumAlpha, DepthBits, StencilBits,
            AuxBuffers, LayerType, Reserved;
        public uint LayerMask, VisibleMask, DamageMask;
    }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr CreateWindowEx(uint ex, string cls, string name, uint style, int x, int y,
                                        int w, int h, IntPtr parent, IntPtr menu, IntPtr instance,
                                        IntPtr param);
    [DllImport("user32.dll")]
    static extern IntPtr GetDC(IntPtr window);
    [DllImport("user32.dll")]
    static extern int ReleaseDC(IntPtr window, IntPtr dc);
    [DllImport("user32.dll")]
    static extern bool DestroyWindow(IntPtr window);
    [DllImport("gdi32.dll")]
    static extern int ChoosePixelFormat(IntPtr dc, ref PixelFormat format);
    [DllImport("gdi32.dll")]
    static extern bool SetPixelFormat(IntPtr dc, int index, ref PixelFormat format);
    [DllImport("opengl32.dll")]
    static extern IntPtr wglCreateContext(IntPtr dc);
    [DllImport("opengl32.dll")]
    static extern bool wglMakeCurrent(IntPtr dc, IntPtr context);
    [DllImport("opengl32.dll")]
    static extern bool wglDeleteContext(IntPtr context);
    [DllImport("opengl32.dll")]
    static extern IntPtr wglGetProcAddress(string name);
    [DllImport("opengl32.dll")]
    static extern IntPtr glGetString(uint name);
    [DllImport("opengl32.dll")]
    static extern uint glGetError();
    [DllImport("opengl32.dll")]
    static extern void glGenTextures(int count, out uint id);
    [DllImport("opengl32.dll")]
    static extern void glBindTexture(uint target, uint id);
    [DllImport("opengl32.dll")]
    static extern void glTexParameteri(uint target, uint param, int value);
    [DllImport("opengl32.dll")]
    static extern void glPixelStorei(uint param, int value);
    [DllImport("opengl32.dll")]
    static extern void glTexImage2D(uint target, int level, int format, int width, int height,
                                    int border, uint source, uint type, IntPtr data);
    [DllImport("opengl32.dll")]
    static extern void glGetTexImage(uint target, int level, uint format, uint type, IntPtr data);

    delegate uint CreateShader(uint type);
    delegate void ShaderSource(uint shader, int count, IntPtr strings, IntPtr lengths);
    delegate void CompileShader(uint shader);
    delegate void GetShaderiv(uint shader, uint param, out int value);
    delegate void GetShaderInfoLog(uint shader, int size, out int length, StringBuilder log);
    delegate uint CreateProgram();
    delegate void AttachShader(uint program, uint shader);
    delegate void LinkProgram(uint program);
    delegate void GetProgramiv(uint program, uint param, out int value);
    delegate void GetProgramInfoLog(uint program, int size, out int length, StringBuilder log);
    delegate void UseProgram(uint program);
    delegate int GetUniformLocation(uint program, string name);
    delegate void Uniform4dv(int location, int count, double[] value);
    delegate void Uniform3fv(int location, int count, float[] value);
    delegate void Uniform3iv(int location, int count, int[] value);
    delegate void TexImage3D(uint target, int level, int format, int width, int height, int depth,
                             int border, uint source, uint type, IntPtr data);
    delegate void ActiveTexture(uint unit);
    delegate void BindImageTexture(uint unit, uint texture, int level, bool layered, int layer,
                                   uint access, uint format);
    delegate void DispatchCompute(uint x, uint y, uint z);
    delegate void MemoryBarrier(uint barriers);

    static T Proc<T>(string name)
        where T : class
    {
        IntPtr pointer = wglGetProcAddress(name);
        if (pointer == IntPtr.Zero)
            throw new Exception("OpenGL function unavailable: " + name);
        return Marshal.GetDelegateForFunctionPointer(pointer, typeof(T)) as T;
    }
    static void Check(string phase)
    {
        uint e = glGetError();
        if (e != 0)
            throw new Exception("OpenGL error " + e + " during " + phase);
    }
    static uint Compile(string text)
    {
        uint shader = Proc<CreateShader>("glCreateShader")(0x91B9);
        IntPtr str = Marshal.StringToHGlobalAnsi(text), array = Marshal.AllocHGlobal(IntPtr.Size);
        Marshal.WriteIntPtr(array, str);
        Proc<ShaderSource>("glShaderSource")(shader, 1, array, IntPtr.Zero);
        Marshal.FreeHGlobal(array);
        Marshal.FreeHGlobal(str);
        Proc<CompileShader>("glCompileShader")(shader);
        int good;
        Proc<GetShaderiv>("glGetShaderiv")(shader, 0x8B81, out good);
        if (good == 0)
        {
            var log = new StringBuilder(32768);
            int length;
            Proc<GetShaderInfoLog>("glGetShaderInfoLog")(shader, log.Capacity, out length, log);
            throw new Exception(log.ToString());
        }
        uint program = Proc<CreateProgram>("glCreateProgram")();
        Proc<AttachShader>("glAttachShader")(program, shader);
        Proc<LinkProgram>("glLinkProgram")(program);
        Proc<GetProgramiv>("glGetProgramiv")(program, 0x8B82, out good);
        if (good == 0)
        {
            var log = new StringBuilder(32768);
            int length;
            Proc<GetProgramInfoLog>("glGetProgramInfoLog")(program, log.Capacity, out length, log);
            throw new Exception(log.ToString());
        }
        Proc<UseProgram>("glUseProgram")(program);
        return program;
    }
    class Volume
    {
        public uint Blocks, Coarse;
        public byte[] Palette;
        public int W, L, H;
    }
    static uint Texture(byte[] bytes, int w, int l, int h)
    {
        uint id;
        glGenTextures(1, out id);
        glBindTexture(0x806F, id);
        glTexParameteri(0x806F, 0x2801, 0x2600);
        glTexParameteri(0x806F, 0x2800, 0x2600);
        glTexParameteri(0x806F, 0x2802, 0x812F);
        glTexParameteri(0x806F, 0x2803, 0x812F);
        glTexParameteri(0x806F, 0x8072, 0x812F);
        var pin = GCHandle.Alloc(bytes, GCHandleType.Pinned);
        Proc<TexImage3D>("glTexImage3D")(0x806F, 0, 0x8232, w, l, h, 0, 0x8D94, 0x1401,
                                         pin.AddrOfPinnedObject());
        pin.Free();
        Check("volume upload");
        return id;
    }
    static Volume Load(string path)
    {
        int w, l, h;
        byte[] palette, blocks;
        using (var r = new BinaryReader(File.OpenRead(path)))
        {
            w = r.ReadInt32();
            l = r.ReadInt32();
            h = r.ReadInt32();
            palette = r.ReadBytes(768);
            blocks = r.ReadBytes(w * l * h);
        }
        int cw = (w + 7) / 8, cl = (l + 7) / 8;
        byte[] coarse = new byte[cw * cl * ((h + 7) / 8)];
        for (int y = 0; y < h; y++)
            for (int z = 0; z < l; z++)
                for (int x = 0; x < w; x++)
                    if (blocks[(y * l + z) * w + x] != 0)
                        coarse[((y >> 3) * cl + (z >> 3)) * cw + (x >> 3)] = 1;
        return new Volume { Blocks = Texture(blocks, w, l, h),
                            Coarse = Texture(coarse, cw, cl, (h + 7) / 8),
                            Palette = palette,
                            W = w,
                            L = l,
                            H = h };
    }
    static uint LoadTerrain(string path)
    {
        var atlas = ClassicTerrain.Load(path);
        uint id;
        glGenTextures(1, out id);
        glBindTexture(0x8C1A, id);
        glTexParameteri(0x8C1A, 0x2801, 0x2703);
        glTexParameteri(0x8C1A, 0x2800, 0x2601);
        glTexParameteri(0x8C1A, 0x2802, 0x812F);
        glTexParameteri(0x8C1A, 0x2803, 0x812F);
        glTexParameteri(0x8C1A, 0x813C, 0);
        glTexParameteri(0x8C1A, 0x813D, atlas.Levels - 1);
        var upload = Proc<TexImage3D>("glTexImage3D");
        for (int n = 0; n < atlas.Levels; n++)
        {
            int side = Math.Max(1, atlas.Size >> n);
            var pin = GCHandle.Alloc(atlas.Mips[n], GCHandleType.Pinned);
            upload(0x8C1A, n, 0x8058, side, side, 256, 0, 0x1908, 0x1401, pin.AddrOfPinnedObject());
            pin.Free();
        }
        Check("terrain upload");
        return id;
    }
    static double[] Parameters(OrbitFrame f)
    {
        double a = f.Azimuth * Math.PI / 180, e = f.Elevation * Math.PI / 180;
        return new double[] { f.CenterX,
                              f.CenterY,
                              f.CenterZ,
                              f.Scale,
                              Math.Sin(a) * Math.Cos(e),
                              -Math.Sin(e),
                              Math.Cos(a) * Math.Cos(e),
                              f.FocusFloor,
                              -Math.Cos(a),
                              0,
                              Math.Sin(a),
                              f.ContextAlpha,
                              Math.Sin(a) * Math.Sin(e),
                              Math.Cos(e),
                              Math.Cos(a) * Math.Sin(e),
                              f.SweepX,
                              f.XMin,
                              f.XMax,
                              f.ZMin,
                              f.ZMax,
                              f.FocusXMin,
                              f.FocusXMax,
                              f.FocusZMin,
                              f.FocusZMax,
                              f.ClosedFocusXMin,
                              f.ClosedFocusXMax,
                              f.ClosedFocusZMin,
                              f.ClosedFocusZMax,
                              f.CutOpen,
                              f.CutClosed,
                              f.Width,
                              f.Height,
                              f.Mode == "slice" ? 1 : (f.Mode == "ghost" ? 2 : 0),
                              0,
                              0,
                              (f.FullCubeSlabs ? 1 : 0) +
                                  (String.IsNullOrEmpty(f.Terrain) ? 0 : 2) +
                                  (f.MarkedBlocks ? 4 : 0),
                              f.YMin,
                              f.YMax,
                              f.RayOffset,
                              f.ShadowDistance,
                              f.RaySteps,
                              f.ShadowSteps,
                              0,
                              0 };
    }
    static void Main(string[] args)
    {
        var window = CreateWindowEx(0, "STATIC", "MineTrek Cutaway offscreen renderer", 0, 0, 0, 1,
                                    1, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
        if (window == IntPtr.Zero)
            throw new Exception("Could not create hidden OpenGL surface");
        IntPtr dc = GetDC(window);
        var pf = new PixelFormat { Size = (ushort)Marshal.SizeOf(typeof(PixelFormat)), Version = 1,
                                   Flags = 0x24, ColorBits = 32, AlphaBits = 8 };
        if (!SetPixelFormat(dc, ChoosePixelFormat(dc, ref pf), ref pf))
            throw new Exception("Could not set pixel format");
        IntPtr context = wglCreateContext(dc);
        if (!wglMakeCurrent(dc, context))
            throw new Exception("Could not initialize OpenGL context");
        try
        {
            string renderer = Marshal.PtrToStringAnsi(glGetString(0x1F01));
            Console.Error.WriteLine("GPU: " + renderer + " / " +
                                    Marshal.PtrToStringAnsi(glGetString(0x1F02)));
            glPixelStorei(0x0CF5, 1);
            glPixelStorei(0x0D05, 1);
            string shader = File.ReadAllText(
                args.Length > 3
                    ? args[3]
                    : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "voxel.comp"));
            uint program = Compile(shader);
            var uniform = Proc<Uniform4dv>("glUniform4dv");
            var colors = Proc<Uniform3fv>("glUniform3fv");
            var location = Proc<GetUniformLocation>("glGetUniformLocation");
            int ploc = location(program, "p[0]"), cloc = location(program, "palette[0]");
            Proc<Uniform3iv>("glUniform3iv")(location(program, "tileFaces[0]"), 50,
                                             ClassicTerrain.Faces);
            var active = Proc<ActiveTexture>("glActiveTexture");
            var bind = Proc<BindImageTexture>("glBindImageTexture");
            var dispatch = Proc<DispatchCompute>("glDispatchCompute");
            var barrier = Proc<MemoryBarrier>("glMemoryBarrier");
            var serializer = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            var jobs = serializer.Deserialize<List<OrbitFrame>>(File.ReadAllText(args[2]));
            var volumes = new Dictionary<string, Volume>(StringComparer.OrdinalIgnoreCase);
            var terrains = new Dictionary<string, uint>(StringComparer.OrdinalIgnoreCase);
            uint output;
            glGenTextures(1, out output);
            int width = 0, height = 0;
            for (int i = 0; i < jobs.Count; i++)
            {
                var f = jobs[i];
                string path = String.IsNullOrEmpty(f.Volume) ? args[1] : f.Volume;
                Volume v;
                if (!volumes.TryGetValue(path, out v))
                {
                    v = Load(path);
                    volumes[path] = v;
                }
                if (f.XMax <= 0)
                    f.XMax = v.W;
                if (f.ZMax <= 0)
                    f.ZMax = v.L;
                if (f.YMax <= 0)
                    f.YMax = v.H;
                active(0x84C0);
                glBindTexture(0x0DE1, output);
                glTexParameteri(0x0DE1, 0x2801, 0x2600);
                glTexParameteri(0x0DE1, 0x2800, 0x2600);
                glTexParameteri(0x0DE1, 0x813C, 0);
                glTexParameteri(0x0DE1, 0x813D, 0);
                if (f.Width != width || f.Height != height)
                {
                    width = f.Width;
                    height = f.Height;
                    glTexImage2D(0x0DE1, 0, 0x8058, width, height, 0, 0x1908, 0x1401, IntPtr.Zero);
                }
                bind(0, output, 0, false, 0, 0x88B9, 0x8058);
                active(0x84C1);
                glBindTexture(0x806F, v.Blocks);
                active(0x84C2);
                glBindTexture(0x806F, v.Coarse);
                if (!String.IsNullOrEmpty(f.Terrain))
                {
                    active(0x84C3);
                    uint terrain;
                    if (!terrains.TryGetValue(f.Terrain, out terrain))
                    {
                        terrain = LoadTerrain(f.Terrain);
                        terrains[f.Terrain] = terrain;
                    }
                    glBindTexture(0x8C1A, terrain);
                }
                float[] palette = new float[768];
                for (int n = 0; n < 768; n++)
                    palette[n] = v.Palette[n];
                colors(cloc, 256, palette);
                double[] parameters = Parameters(f);
                // Small dispatches keep the desktop responsive and avoid a
                // long unpreempted 4K compute workload on the display GPU.
                for (int y = 0; y < height; y += 256)
                    for (int x = 0; x < width; x += 512)
                    {
                        parameters[33] = x;
                        parameters[34] = y;
                        uniform(ploc, 11, parameters);
                        dispatch(32, 32, 1);
                    }
                barrier(0x20 | 0x100);
                byte[] pixels = new byte[width * height * 4];
                var pin = GCHandle.Alloc(pixels, GCHandleType.Pinned);
                active(0x84C0);
                glBindTexture(0x0DE1, output);
                glGetTexImage(0x0DE1, 0, 0x1908, 0x1401, pin.AddrOfPinnedObject());
                pin.Free();
                Check("frame " + i);
                File.WriteAllBytes(f.Output, pixels);
                Console.WriteLine(i);
                Console.Out.Flush();
            }
        }
        finally
        {
            wglMakeCurrent(IntPtr.Zero, IntPtr.Zero);
            wglDeleteContext(context);
            ReleaseDC(window, dc);
            DestroyWindow(window);
        }
    }
}

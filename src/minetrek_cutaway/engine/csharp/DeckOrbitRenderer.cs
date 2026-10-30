using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Web.Script.Serialization;
using System.Threading.Tasks;

public class OrbitFrame
{
    public string Name, Output, Mode;
    public string Volume;
    // Diagnostic switch only: production uses the Classic bottom half slab.
    public bool FullCubeSlabs, MarkedBlocks;
    public int YMin = 0, YMax = 0, RaySteps = 2000, ShadowSteps = 1800;
    public double RayOffset = 1500, ShadowDistance = 1100;
    public string Terrain;
    public int Width, Height, XMin = 0, XMax = 0, ZMin = 0, ZMax = 0;
    public double Azimuth, Elevation, CenterX, CenterY, CenterZ, Scale;
    public double FocusFloor, CutOpen, CutClosed, SweepX, ContextAlpha = 0.15;
    public double FocusXMin, FocusXMax, FocusZMin, FocusZMax;
    public double ClosedFocusXMin, ClosedFocusXMax, ClosedFocusZMin, ClosedFocusZMax;
}

public class ClassicTerrain
{
    // Classic block IDs 0..49: top, side, bottom tile in the 16-column atlas.
    // ClassiCube src/Block.c DefaultSet preserves the original Classic layout.
    public static readonly int[] Faces = {
        0,  0,  0,  1,  1,  1,  0,  3,  2,  2,  2,  2,  16, 16, 16, 4,  4,  4,  15, 15, 15, 17,
        17, 17, 14, 14, 14, 14, 14, 14, 30, 30, 30, 30, 30, 30, 18, 18, 18, 19, 19, 19, 32, 32,
        32, 33, 33, 33, 34, 34, 34, 21, 20, 21, 22, 22, 22, 48, 48, 48, 49, 49, 49, 64, 64, 64,
        65, 65, 65, 66, 66, 66, 67, 67, 67, 68, 68, 68, 69, 69, 69, 70, 70, 70, 71, 71, 71, 72,
        72, 72, 73, 73, 73, 74, 74, 74, 75, 75, 75, 76, 76, 76, 77, 77, 77, 78, 78, 78, 79, 79,
        79, 13, 13, 13, 12, 12, 12, 29, 29, 29, 28, 28, 28, 24, 40, 56, 23, 39, 55, 6,  5,  6,
        6,  5,  6,  7,  7,  7,  9,  8,  10, 4,  35, 4,  36, 36, 36, 37, 37, 37
    };
    public int Size, Levels;
    public byte[][] Mips;
    public static ClassicTerrain Load(string path)
    {
        using (var r = new BinaryReader(File.OpenRead(path)))
        {
            var atlas = new ClassicTerrain();
            atlas.Size = r.ReadInt32();
            int count = r.ReadInt32();
            atlas.Levels = r.ReadInt32();
            if (count != 256)
                throw new Exception("Invalid Classic texture tile count");
            atlas.Mips = new byte[atlas.Levels][];
            for (int n = 0; n < atlas.Levels; n++)
            {
                int s = Math.Max(1, atlas.Size >> n);
                atlas.Mips[n] = r.ReadBytes(s * s * 256 * 4);
                if (atlas.Mips[n].Length != s * s * 256 * 4)
                    throw new Exception("Truncated terrain");
            }
            return atlas;
        }
    }
    double Bilinear(int level, int tile, double u, double v, int channel)
    {
        int side = Math.Max(1, Size >> level);
        double x = u * side - .5, y = v * side - .5;
        int ix = (int)Math.Floor(x), iy = (int)Math.Floor(y);
        double fx = x - ix, fy = y - iy, value = 0;
        for (int q = 0; q < 2; q++)
            for (int r = 0; r < 2; r++)
            {
                int ax = Math.Max(0, Math.Min(side - 1, ix + q)),
                    ay = Math.Max(0, Math.Min(side - 1, iy + r));
                value += Mips[level][((tile * side + ay) * side + ax) * 4 + channel] *
                         (q == 0 ? 1 - fx : fx) * (r == 0 ? 1 - fy : fy);
            }
        return value;
    }
    public double Sample(int tile, double u, double v, double lod, int channel)
    {
        lod = Math.Max(0, Math.Min(Levels - 1, lod));
        int lo = (int)lod, hi = Math.Min(Levels - 1, lo + 1);
        return Bilinear(lo, tile, u, v, channel) * (1 - (lod - lo)) +
               Bilinear(hi, tile, u, v, channel) * (lod - lo);
    }
    public bool Opaque(int tile, double u, double v, double lod)
    {
        int level = Math.Max(0, Math.Min(Levels - 1, (int)Math.Floor(lod))),
            side = Math.Max(1, Size >> level);
        int x = Math.Max(0, Math.Min(side - 1, (int)(u * side))),
            y = Math.Max(0, Math.Min(side - 1, (int)(v * side)));
        return Mips[level][((tile * side + y) * side + x) * 4 + 3] >= 128;
    }
    public static void UV(int id, int axis, double dx, double dy, double dz, double x, double y,
                          double z, out int tile, out double u, out double v)
    {
        x -= Math.Floor(x);
        y -= Math.Floor(y);
        z -= Math.Floor(z);
        u = axis == 0 ? z : x;
        v = axis == 1 ? z : 1 - y;
        if (axis == 0 && dx < 0)
            u = 1 - u;
        if (axis == 2 && dz > 0)
            u = 1 - u;
        if (axis == 1 && dy > 0)
            v = 1 - v;
        tile = Faces[id * 3 + (axis == 1 ? (dy < 0 ? 0 : 2) : 1)];
    }
}

class DeckOrbitRenderer
{
    class VolumeData
    {
        public byte[] Blocks, Coarse, Palette;
        public int W, L, H;
    }
    static int W, L, H, CW, CL;
    static byte[] Blocks, Palette, Coarse;
    static ClassicTerrain Terrain;
    static int Index(int x, int y, int z)
    {
        return (y * L + z) * W + x;
    }
    static bool World(int x, int y, int z)
    {
        return x >= 0 && x < W && y >= 0 && y < H && z >= 0 && z < L;
    }

    static void Load(string path)
    {
        using (var r = new BinaryReader(File.OpenRead(path)))
        {
            W = r.ReadInt32();
            L = r.ReadInt32();
            H = r.ReadInt32();
            Palette = r.ReadBytes(768);
            Blocks = r.ReadBytes(W * L * H);
        }
        if (Blocks.Length != W * L * H)
            throw new Exception("Truncated voxel input");
    }

    static void BuildCoarse()
    {
        CW = (W + 7) / 8;
        CL = (L + 7) / 8;
        Coarse = new byte[CW * CL * ((H + 7) / 8)];
        Parallel.For(0, H,
                     y =>
                     {
                         for (int z = 0; z < L; z++)
                             for (int x = 0; x < W; x++)
                                 if (Blocks[Index(x, y, z)] != 0)
                                     Coarse[((y >> 3) * CL + (z >> 3)) * CW + (x >> 3)] = 1;
                     });
    }

    static bool Solid(int x, int y, int z, OrbitFrame f)
    {
        if (x < f.XMin || x >= f.XMax || z < f.ZMin || z >= f.ZMax || y < f.YMin || y >= f.YMax ||
            !World(x, y, z))
            return false;
        if (f.Mode == "slice" && y < f.FocusFloor)
            return false;
        bool opened = x + 0.5 >= f.SweepX;
        double xmin = opened ? f.FocusXMin : f.ClosedFocusXMin,
               xmax = opened ? f.FocusXMax : f.ClosedFocusXMax;
        double zmin = opened ? f.FocusZMin : f.ClosedFocusZMin,
               zmax = opened ? f.FocusZMax : f.ClosedFocusZMax;
        if (f.Mode == "ghost" && y >= f.FocusFloor &&
            (x < xmin || x >= xmax || z < zmin || z >= zmax))
            return false;
        double cut = opened ? f.CutOpen : f.CutClosed;
        byte raw = Blocks[Index(x, y, z)];
        if (f.MarkedBlocks && raw >= 128 && !opened)
            return false;
        return y < cut && BlockId(x, y, z, f) != 0;
    }

    static int BlockId(int x, int y, int z, OrbitFrame f)
    {
        return f.MarkedBlocks ? Blocks[Index(x, y, z)] & 127 : Blocks[Index(x, y, z)];
    }

    static bool SolidAt(double x, double y, double z, OrbitFrame f)
    {
        int bx = (int)Math.Floor(x), by = (int)Math.Floor(y), bz = (int)Math.Floor(z);
        return Solid(bx, by, bz, f) &&
               (f.FullCubeSlabs || BlockId(bx, by, bz, f) != 44 || y - by < .5);
    }

    // Intersect the occupied shape inside a DDA cell. A ray crossing the empty
    // upper half must still be allowed to enter the lower half before exiting.
    static bool BlockHit(int x, int y, int z, double ox, double oy, double oz, double dx, double dy,
                         double dz, OrbitFrame f, ref double t, ref int axis)
    {
        if (f.FullCubeSlabs || BlockId(x, y, z, f) != 44)
            return true;
        double near = -1e30, far = 1e30;
        int face = 1;
        if (!Slab(ox, dx, x, x + 1, 0, ref near, ref far, ref face) ||
            !Slab(oy, dy, y, y + .5, 1, ref near, ref far, ref face) ||
            !Slab(oz, dz, z, z + 1, 2, ref near, ref far, ref face) || far <= t)
            return false;
        if (near >= t - .000002)
        {
            t = near + .000001;
            axis = face;
        }
        return true;
    }

    static double Next(double o, double d, int coordinate, int jump)
    {
        if (Math.Abs(d) < 1e-10)
            return 1e30;
        return (((coordinate / jump + (d > 0 ? 1 : 0)) * jump) - o) / d;
    }

    static bool Shadow(double ox, double oy, double oz, double dx, double dy, double dz,
                       OrbitFrame f)
    {
        double t = 0.001;
        int axis = 1;
        for (int i = 0; i < f.ShadowSteps && t < f.ShadowDistance; i++)
        {
            double fx = ox + dx * t, fy = oy + dy * t, fz = oz + dz * t;
            if (fx < f.XMin || fx >= f.XMax || fz < f.ZMin || fz >= f.ZMax || fy < f.YMin ||
                fy >= Math.Min(f.YMax, Math.Max(f.CutClosed, f.CutOpen)))
                return false;
            int x = (int)fx, y = (int)fy, z = (int)fz;
            int jump = Coarse[((y >> 3) * CL + (z >> 3)) * CW + (x >> 3)] == 0 ? 8 : 1;
            if (jump == 1 && Solid(x, y, z, f) &&
                BlockHit(x, y, z, ox, oy, oz, dx, dy, dz, f, ref t, ref axis))
            {
                int id = BlockId(x, y, z, f), tile;
                double u, v;
                if (Terrain == null || id >= 50)
                    return true;
                ClassicTerrain.UV(id, axis, dx, dy, dz, ox + dx * t, oy + dy * t, oz + dz * t,
                                  out tile, out u, out v);
                if (Terrain.Opaque(tile, u, v, 0))
                    return true;
            }
            double tx = Next(ox, dx, x, jump), ty = Next(oy, dy, y, jump),
                   tz = Next(oz, dz, z, jump);
            if (tx < ty && tx < tz)
            {
                t = tx + .000001;
                axis = 0;
            }
            else if (ty < tz)
            {
                t = ty + .000001;
                axis = 1;
            }
            else
            {
                t = tz + .000001;
                axis = 2;
            }
        }
        return false;
    }

    static bool Slab(double o, double d, double lo, double hi, int axis, ref double near,
                     ref double far, ref int hitAxis)
    {
        if (Math.Abs(d) < 1e-10)
            return o >= lo && o < hi;
        double a = (lo - o) / d, b = (hi - o) / d;
        if (a > b)
        {
            double c = a;
            a = b;
            b = c;
        }
        if (a > near)
        {
            near = a;
            hitAxis = axis;
        }
        far = Math.Min(far, b);
        return near < far;
    }

    static byte[] Render(OrbitFrame f)
    {
        byte[] pixels = new byte[f.Width * f.Height * 4];
        double a = f.Azimuth * Math.PI / 180, e = f.Elevation * Math.PI / 180;
        double dx = Math.Sin(a) * Math.Cos(e), dy = -Math.Sin(e), dz = Math.Cos(a) * Math.Cos(e);
        // Screen right must oppose the former basis: right x up points toward
        // the viewer, not along the viewing ray. The old basis mirrored text.
        double rx = -Math.Cos(a), rz = Math.Sin(a);
        double ux = Math.Sin(a) * Math.Sin(e), uy = Math.Cos(e), uz = Math.Cos(a) * Math.Sin(e);
        double ymin = f.Mode == "slice" ? Math.Max(f.YMin, f.FocusFloor) : f.YMin;
        double ymax = Math.Min(f.YMax, Math.Max(f.CutClosed, f.CutOpen));
        Parallel.For(
            0, f.Height,
            sy =>
            {
                for (int sx = 0; sx < f.Width; sx++)
                {
                    double px = (sx + 0.5 - f.Width / 2.0) / f.Scale,
                           py = (f.Height / 2.0 - sy - 0.5) / f.Scale;
                    double ox = f.CenterX + rx * px + ux * py - dx * f.RayOffset;
                    double oy = f.CenterY + uy * py - dy * f.RayOffset;
                    double oz = f.CenterZ + rz * px + uz * py - dz * f.RayOffset;
                    double near = -1e30, far = 1e30;
                    int axis = 1;
                    if (!Slab(ox, dx, f.XMin, f.XMax, 0, ref near, ref far, ref axis) ||
                        !Slab(oy, dy, ymin, ymax, 1, ref near, ref far, ref axis) ||
                        !Slab(oz, dz, f.ZMin, f.ZMax, 2, ref near, ref far, ref axis))
                        continue;
                    double t = near + 0.000001;
                    for (int iter = 0; iter < f.RaySteps && t < far; iter++)
                    {
                        double fx = ox + dx * t, fy = oy + dy * t, fz = oz + dz * t;
                        if (fx < f.XMin || fx >= f.XMax || fy < ymin || fy >= ymax || fz < f.ZMin ||
                            fz >= f.ZMax)
                            break;
                        int x = (int)fx, y = (int)fy, z = (int)fz;
                        int jump = Coarse[((y >> 3) * CL + (z >> 3)) * CW + (x >> 3)] == 0 ? 8 : 1;
                        if (jump == 1 && Solid(x, y, z, f) &&
                            BlockHit(x, y, z, ox, oy, oz, dx, dy, dz, f, ref t, ref axis))
                        {
                            int id = BlockId(x, y, z, f);
                            fx = ox + dx * t;
                            fy = oy + dy * t;
                            fz = oz + dz * t;
                            if (Terrain != null && id < 50)
                            {
                                int alphaTile;
                                double au, av;
                                ClassicTerrain.UV(id, axis, dx, dy, dz, fx, fy, fz, out alphaTile,
                                                  out au, out av);
                                // Cutout texels expose the voxels behind the window.
                                if (!Terrain.Opaque(alphaTile, au, av, 0))
                                {
                                    double ax = Next(ox, dx, x, jump), ay = Next(oy, dy, y, jump),
                                           az = Next(oz, dz, z, jump);
                                    if (ax < ay && ax < az)
                                    {
                                        t = ax + .000001;
                                        axis = 0;
                                    }
                                    else if (ay < az)
                                    {
                                        t = ay + .000001;
                                        axis = 1;
                                    }
                                    else
                                    {
                                        t = az + .000001;
                                        axis = 2;
                                    }
                                    continue;
                                }
                            }
                            int nx = axis == 0 ? (dx > 0 ? -1 : 1) : 0;
                            int ny = axis == 1 ? (dy > 0 ? -1 : 1) : 0;
                            int nz = axis == 2 ? (dz > 0 ? -1 : 1) : 0;
                            double diffuse = Math.Max(0, nx * -0.38 + ny * 0.76 + nz * -0.53);
                            int blocked = 0;
                            if (diffuse > 0)
                                for (int k = 0; k < 4; k++)
                                {
                                    double lx = -0.38 + ((k & 1) == 0 ? -0.16 : 0.16),
                                           ly = 0.76 + ((k & 2) == 0 ? -0.16 : 0.16), lz = -0.53;
                                    double len = Math.Sqrt(lx * lx + ly * ly + lz * lz);
                                    if (Shadow(fx + nx * .02, fy + ny * .02, fz + nz * .02,
                                               lx / len, ly / len, lz / len, f))
                                        blocked++;
                                }
                            double vis = 1 - 0.55 * blocked / 4.0;
                            int neighbors = 0;
                            for (int q = -1; q <= 1; q++)
                                for (int r = -1; r <= 1; r++)
                                {
                                    if (q == 0 && r == 0)
                                        continue;
                                    bool solid =
                                        axis == 0
                                            ? SolidAt(fx + nx * .02, fy + q, z + r + .5, f)
                                            : (axis == 1
                                                   ? SolidAt(x + q + .5, fy + ny * .02, z + r + .5,
                                                             f)
                                                   : SolidAt(x + q + .5, fy + r, fz + nz * .02, f));
                                    if (solid)
                                        neighbors++;
                                }
                            double shade = 1 - 0.34 * neighbors / 8.0;
                            double u = axis == 0 ? fz - z : fx - x, v = axis == 1 ? fz - z : fy - y;
                            double vMax = axis != 1 && id == 44 && !f.FullCubeSlabs ? .5 : 1;
                            if (u < .045 || u > .955 || v < .045 || v > vMax - .045)
                                shade *= .90;
                            int hash = unchecked(x * 73856093 ^ y * 19349663 ^ z * 83492791);
                            shade *= .97 + (hash & 255) / 255.0 * .06;
                            int p = (sy * f.Width + sx) * 4;
                            double tu = u, tv = 1 - v, lod = 0;
                            int tile = 0;
                            if (Terrain != null && id < 50)
                            {
                                if (axis == 0 && nx > 0)
                                    tu = 1 - tu;
                                if (axis == 2 && nz < 0)
                                    tu = 1 - tu;
                                if (axis == 1)
                                    tv = ny > 0 ? v : 1 - v;
                                tile = ClassicTerrain
                                           .Faces[id * 3 + (axis == 1 ? (ny > 0 ? 0 : 2) : 1)];
                                double da = axis == 0 ? dx : (axis == 1 ? dy : dz),
                                       ra = axis == 0 ? rx : (axis == 1 ? 0 : rz),
                                       ua = axis == 0 ? ux : (axis == 1 ? uy : uz);
                                double ur = axis == 0 ? rz - dz * ra / da : rx - dx * ra / da;
                                double vr = axis == 1 ? rz - dz * ra / da : -dy * ra / da;
                                double uu = axis == 0 ? uz - dz * ua / da : ux - dx * ua / da;
                                double vu = axis == 1 ? uz - dz * ua / da : uy - dy * ua / da;
                                double footprint = Math.Max(Math.Sqrt(ur * ur + vr * vr),
                                                            Math.Sqrt(uu * uu + vu * vu)) /
                                                   f.Scale;
                                lod = Math.Log(Math.Max(1e-12, Terrain.Size * footprint), 2);
                            }
                            for (int c = 0; c < 3; c++)
                            {
                                double key = c == 0 ? 1.0 : (c == 1 ? .97 : .93),
                                       fill = c == 0 ? .87 : (c == 1 ? .93 : 1.0);
                                double color = Terrain != null && id < 50
                                                   ? Terrain.Sample(tile, tu, tv, lod, c)
                                                   : Palette[id * 3 + c];
                                double value = color * shade *
                                                   (.54 * fill + .64 * diffuse * vis * key) * 1.15 +
                                               3;
                                pixels[p + c] = (byte)Math.Min(255, Math.Max(0, value));
                            }
                            double alpha = 1.0;
                            if (f.Mode == "ghost")
                            {
                                double focus =
                                    Math.Max(0, Math.Min(1, (y + 1.0 - f.FocusFloor) / 0.8));
                                bool opened = x + 0.5 >= f.SweepX;
                                double xmin = opened ? f.FocusXMin : f.ClosedFocusXMin,
                                       xmax = opened ? f.FocusXMax : f.ClosedFocusXMax;
                                double zmin = opened ? f.FocusZMin : f.ClosedFocusZMin,
                                       zmax = opened ? f.FocusZMax : f.ClosedFocusZMax;
                                double awayX = Math.Max(0, Math.Max(xmin - x, x + 1 - xmax)),
                                       awayZ = Math.Max(0, Math.Max(zmin - z, z + 1 - zmax));
                                double context =
                                    f.ContextAlpha *
                                    Math.Exp(-Math.Max(0, f.FocusFloor - y) / 12.0 -
                                             Math.Sqrt(awayX * awayX + awayZ * awayZ) / 18.0);
                                alpha = context + (1 - context) * focus;
                            }
                            pixels[p + 3] = (byte)Math.Round(255 * alpha);
                            break;
                        }
                        double tx = Next(ox, dx, x, jump), ty = Next(oy, dy, y, jump),
                               tz = Next(oz, dz, z, jump);
                        if (tx < ty && tx < tz)
                        {
                            t = tx + 0.000001;
                            axis = 0;
                        }
                        else if (ty < tz)
                        {
                            t = ty + 0.000001;
                            axis = 1;
                        }
                        else
                        {
                            t = tz + 0.000001;
                            axis = 2;
                        }
                    }
                }
            });
        return pixels;
    }

    static void Main(string[] args)
    {
        var serializer = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
        Load(args[1]);
        BuildCoarse();
        string defaultVolume = Path.GetFullPath(args[1]);
        var volumes = new Dictionary<string, VolumeData>(StringComparer.OrdinalIgnoreCase);
        volumes[defaultVolume] =
            new VolumeData { Blocks = Blocks, Coarse = Coarse, Palette = Palette,
                             W = W,           L = L,           H = H };
        var frames = serializer.Deserialize<List<OrbitFrame>>(File.ReadAllText(args[2]));
        var terrains = new Dictionary<string, ClassicTerrain>(StringComparer.OrdinalIgnoreCase);
        for (int i = 0; i < frames.Count; i++)
        {
            var f = frames[i];
            string key =
                String.IsNullOrEmpty(f.Volume) ? defaultVolume : Path.GetFullPath(f.Volume);
            VolumeData volume;
            if (!volumes.TryGetValue(key, out volume))
            {
                Load(key);
                BuildCoarse();
                volume = new VolumeData { Blocks = Blocks, Coarse = Coarse, Palette = Palette,
                                          W = W,           L = L,           H = H };
                volumes[key] = volume;
            }
            Blocks = volume.Blocks;
            Coarse = volume.Coarse;
            Palette = volume.Palette;
            W = volume.W;
            L = volume.L;
            H = volume.H;
            CW = (W + 7) / 8;
            CL = (L + 7) / 8;
            if (f.XMax <= 0)
                f.XMax = W;
            if (f.ZMax <= 0)
                f.ZMax = L;
            if (f.YMax <= 0)
                f.YMax = H;
            Terrain = null;
            if (!String.IsNullOrEmpty(f.Terrain))
            {
                if (!terrains.TryGetValue(f.Terrain, out Terrain))
                {
                    Terrain = ClassicTerrain.Load(f.Terrain);
                    terrains[f.Terrain] = Terrain;
                }
            }
            File.WriteAllBytes(f.Output, Render(f));
            Console.WriteLine(i);
            Console.Out.Flush();
        }
    }
}

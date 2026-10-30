using System;
using System.Reflection;

class ClassicGeometryChecks
{
    static Type R = typeof(DeckOrbitRenderer);
    static BindingFlags Flags = BindingFlags.Static | BindingFlags.NonPublic;
    static void Set(string name, object value)
    {
        R.GetField(name, Flags).SetValue(null, value);
    }
    static void Require(bool test, string message)
    {
        if (!test)
            throw new Exception(message);
        Console.WriteLine("PASS " + message);
    }
    static bool Hit(double ox, double oy, double oz, double dx, double dy, double dz, double t,
                    OrbitFrame f, out double result, out int axis)
    {
        object[] args = { 6, 3, 6, ox, oy, oz, dx, dy, dz, f, t, 0 };
        bool ok = (bool)R.GetMethod("BlockHit", Flags).Invoke(null, args);
        result = (double)args[10];
        axis = (int)args[11];
        return ok;
    }
    static bool Shadow(double x, double y, double z, double dx, double dy, double dz, OrbitFrame f)
    {
        return (bool)R.GetMethod("Shadow", Flags)
            .Invoke(null, new object[] { x, y, z, dx, dy, dz, f });
    }
    static void Main()
    {
        Set("W", 16);
        Set("L", 16);
        Set("H", 8);
        byte[] blocks = new byte[16 * 16 * 8];
        int index = (3 * 16 + 6) * 16 + 6;
        blocks[index] = 44;
        Set("Blocks", blocks);
        R.GetMethod("BuildCoarse", Flags).Invoke(null, null);
        var f =
            new OrbitFrame { Mode = "remaining", YMax = 8,    XMin = 2,      XMax = 14,   ZMin = 2,
                             ZMax = 14,          CutOpen = 8, CutClosed = 8, SweepX = -30 };
        double t;
        int axis;
        Require(Hit(6.5, 5, 6.5, 0, -1, 0, 1.000001, f, out t, out axis) &&
                    Math.Abs(t - 1.500001) < 1e-8 && axis == 1,
                "slab top is y + 0.5");
        Require(!Hit(5, 3.75, 6.5, 1, 0, 0, 1.000001, f, out t, out axis),
                "upper half passes the camera ray");
        Require(Hit(5, 3.25, 6.5, 1, 0, 0, 1.000001, f, out t, out axis),
                "lower half stops the camera ray");
        Require(Hit(5, 4, 6.5, 1, -.4, 0, 1.000001, f, out t, out axis) &&
                    Math.Abs(t - 1.250001) < 1e-8 && axis == 1,
                "ray entering empty upper half can hit the slab top inside the same cell");
        Require(!Shadow(5, 3.75, 6.5, 1, 0, 0, f), "upper half passes shadow rays");
        Require(Shadow(5, 3.25, 6.5, 1, 0, 0, f), "lower half casts a shadow");
        Require(!Shadow(6.5, 3.52, 6.5, 0, 1, 0, f), "top surface does not shadow itself");
        blocks[index] = 43;
        Require(Shadow(5, 3.75, 6.5, 1, 0, 0, f), "double slab retains full height");
        Require(ClassicTerrain.Faces.Length == 150 && ClassicTerrain.Faces[44 * 3] == 6 &&
                    ClassicTerrain.Faces[44 * 3 + 1] == 5,
                "Classic face mapping includes slab top and side textures");
    }
}

using System.IO;
using System.Security.Cryptography;

namespace JerseyModder.Wpf.Services;

public static class ProjectWorkspace
{
    private static readonly string[] AssetFolders = ["logos", "trims", "numbers", "textures"];

    public static string Create(string parentFolder, string projectName)
    {
        var safeName = SafeName(projectName);
        if (string.IsNullOrWhiteSpace(safeName))
            throw new InvalidOperationException("Enter a project name.");

        var folder = Path.Combine(parentFolder, safeName);
        var projectFile = Path.Combine(folder, $"{safeName}.nba2kproject.json");
        if (File.Exists(projectFile))
            throw new IOException("A project with this name already exists in that location.");

        EnsureStructure(projectFile);
        return projectFile;
    }

    public static void EnsureStructure(string projectFile)
    {
        var root = Path.GetDirectoryName(Path.GetFullPath(projectFile))
            ?? throw new InvalidOperationException("The project location is invalid.");
        Directory.CreateDirectory(root);
        foreach (var folder in AssetFolders)
            Directory.CreateDirectory(Path.Combine(root, "assets", folder));
        Directory.CreateDirectory(Path.Combine(root, "exports"));
    }

    public static string StoreAsset(string projectFile, string category, string sourcePath, string label)
    {
        if (!File.Exists(sourcePath)) throw new FileNotFoundException("The selected image no longer exists.", sourcePath);
        EnsureStructure(projectFile);
        var projectRoot = Path.GetDirectoryName(Path.GetFullPath(projectFile))!;
        var destinationFolder = Path.Combine(projectRoot, "assets", SafeName(category).ToLowerInvariant());
        Directory.CreateDirectory(destinationFolder);

        var sourceFullPath = Path.GetFullPath(sourcePath);
        if (string.Equals(Path.GetDirectoryName(sourceFullPath), destinationFolder, StringComparison.OrdinalIgnoreCase))
            return sourceFullPath;

        using var stream = File.OpenRead(sourceFullPath);
        var hash = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant()[..10];
        var extension = Path.GetExtension(sourceFullPath).ToLowerInvariant();
        var destination = Path.Combine(destinationFolder, $"{SafeName(label).ToLowerInvariant()}_{hash}{extension}");
        if (!File.Exists(destination)) File.Copy(sourceFullPath, destination);
        return destination;
    }

    public static string DisplayName(string projectFile)
    {
        var name = Path.GetFileNameWithoutExtension(projectFile);
        return name.EndsWith(".nba2kproject", StringComparison.OrdinalIgnoreCase)
            ? name[..^".nba2kproject".Length]
            : name;
    }

    public static string SafeName(string value)
    {
        var invalid = Path.GetInvalidFileNameChars();
        var cleaned = new string(value.Trim().Select(character => invalid.Contains(character) ? '_' : character).ToArray());
        return cleaned.Trim().TrimEnd('.');
    }
}

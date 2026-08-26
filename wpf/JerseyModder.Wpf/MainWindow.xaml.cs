using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using JerseyModder.Wpf.Models;
using JerseyModder.Wpf.Services;
using JerseyModder.Wpf.Views;
using Microsoft.Win32;

namespace JerseyModder.Wpf;

public partial class MainWindow : Window
{
    private readonly WorkspaceContext _context;
    private readonly Dictionary<string, ToolPageBase> _pages;
    private bool _syncingScope;
    private ProjectStore? _subscribedProject;

    public MainWindow(ProjectStore? initialProject = null)
    {
        InitializeComponent();
        var root = ProjectWorkspace.ApplicationRoot;
        _context = new WorkspaceContext(root);
        if (initialProject is not null) _context.ReplaceProject(initialProject);
        _context.StatusChanged += (_, message) => Dispatcher.Invoke(() => StatusText.Text = message);
        _context.ProjectReplaced += (_, _) => Dispatcher.Invoke(SyncProject);
        _context.ProjectPathChanged += (_, _) => Dispatcher.Invoke(SyncProject);
        SubscribeToProject();
        _pages = new()
        {
            ["generator"] = new GeneratorPage(_context), ["logo"] = new LogoCreatorPage(_context),
            ["trim"] = new TrimCreatorPage(_context), ["paths"] = new TrimPathPage(_context),
            ["number"] = new NumberEditorPage(_context), ["tweak"] = new TweakEditorPage(_context),
            ["texture"] = new TextureCreatorPage(_context), ["iff"] = new IffTexturesPage(_context),
            ["rdat"] = new RdatEditorPage(_context), ["template"] = new TemplateEditorPage(_context),
        };
        SyncProject();
        PageHost.Content = _pages["generator"];
        Loaded += async (_, _) =>
        {
            try { await _context.Bridge.CallAsync("ping"); StatusText.Text = "Python engine ready."; }
            catch (Exception ex) { Error("Python Engine", ex); }
        };
    }

    private void OnProjectChanged(object? sender, EventArgs e) => Dispatcher.Invoke(() =>
    {
        ProjectState.Text = _context.Project.IsDirty ? "Unsaved changes" : "Saved";
        SyncScope();
    });

    private void SyncProject()
    {
        SubscribeToProject();
        ProjectName.Text = _context.Project.FilePath is null ? "Untitled project" : ProjectWorkspace.DisplayName(_context.Project.FilePath);
        ProjectState.Text = _context.Project.IsDirty ? "Unsaved changes" : "Ready";
        SyncScope();
    }

    private void SubscribeToProject()
    {
        if (ReferenceEquals(_subscribedProject, _context.Project)) return;
        if (_subscribedProject is not null) _subscribedProject.Changed -= OnProjectChanged;
        _subscribedProject = _context.Project;
        _subscribedProject.Changed += OnProjectChanged;
    }

    private void SyncScope()
    {
        _syncingScope = true;
        GarmentPicker.SelectedIndex = _context.Project.Garment == "Shorts" ? 1 : 0;
        PopulateTemplates();
        TemplatePicker.SelectedItem = _context.Project.TemplateName;
        if (TemplatePicker.SelectedIndex < 0) TemplatePicker.SelectedIndex = 0;
        _syncingScope = false;
    }

    private void PopulateTemplates()
    {
        TemplatePicker.Items.Clear();
        foreach (var value in _context.Project.Garment == "Shorts" ? new[] { "Retro shorts", "Classic shorts", "Modern shorts" } : new[] { "Retro U" })
            TemplatePicker.Items.Add(value);
    }

    private void OnGarmentChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_syncingScope || GarmentPicker.SelectedItem is not ComboBoxItem item) return;
        _context.Project.Garment = item.Content?.ToString() ?? "Jersey";
        _syncingScope = true; PopulateTemplates(); TemplatePicker.SelectedIndex = 0; _syncingScope = false;
        _context.Project.TemplateName = TemplatePicker.SelectedItem?.ToString() ?? (_context.Project.Garment == "Shorts" ? "Retro shorts" : "Retro U");
    }

    private void OnTemplateChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_syncingScope && TemplatePicker.SelectedItem is string value) _context.Project.TemplateName = value;
    }

    private void OnNavigation(object sender, RoutedEventArgs e)
    {
        if (!IsLoaded || sender is not RadioButton { Tag: string key } || !_pages.TryGetValue(key, out var page)) return;
        PageHost.Content = page;
    }

    private async void OnNew(object sender, RoutedEventArgs e) => await CreateNewProjectAsync(true);

    private async Task<bool> CreateNewProjectAsync(bool confirmDiscard)
    {
        if (confirmDiscard && !ConfirmDiscard()) return false;
        var dialog = new NewProjectDialog { Owner = this };
        if (dialog.ShowDialog() != true) return false;
        try
        {
            var path = ProjectWorkspace.Create(dialog.ParentFolder, dialog.ProjectName);
            var project = new ProjectStore();
            await project.SaveAsync(path);
            _context.ReplaceProject(project);
            GeneratorNav.IsChecked = true;
            StatusText.Text = $"Created {ProjectWorkspace.DisplayName(path)}.";
            return true;
        }
        catch (Exception ex) { Error("Create Project", ex); return false; }
    }

    private async void OnOpen(object sender, RoutedEventArgs e) => await OpenProjectAsync(true);

    private async Task<bool> OpenProjectAsync(bool confirmDiscard)
    {
        if (confirmDiscard && !ConfirmDiscard()) return false;
        var dialog = new OpenFileDialog { Title = "Open jersey project", Filter = "NBA 2K projects (*.nba2kproject.json;*.json)|*.nba2kproject.json;*.json|All files|*.*" };
        if (dialog.ShowDialog(this) != true) return false;
        try
        {
            ProjectWorkspace.EnsureStructure(dialog.FileName);
            _context.ReplaceProject(await ProjectStore.LoadAsync(dialog.FileName));
            GeneratorNav.IsChecked = true;
            StatusText.Text = $"Opened {ProjectWorkspace.DisplayName(dialog.FileName)}.";
            return true;
        }
        catch (Exception ex) { Error("Open Project", ex); return false; }
    }

    private async void OnSave(object sender, RoutedEventArgs e)
    {
        var path = _context.Project.FilePath;
        if (path is null)
        {
            var dialog = new NewProjectDialog { Owner = this };
            if (dialog.ShowDialog() != true) return;
            try { path = ProjectWorkspace.Create(dialog.ParentFolder, dialog.ProjectName); }
            catch (Exception ex) { Error("Save Project", ex); return; }
        }
        try { await _context.Project.SaveAsync(path); SyncProject(); StatusText.Text = $"Saved {Path.GetFileName(path)}."; }
        catch (Exception ex) { Error("Save Project", ex); }
    }

    private async void OnExport(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFolderDialog { Title = "Choose export package folder", Multiselect = false };
        if (dialog.ShowDialog(this) != true) return;
        try
        {
            StatusText.Text = "Creating export package...";
            var result = (await _context.Bridge.CallAsync("export_package", new { project = _context.Project.Snapshot(), folder = dialog.FolderName }))!.AsObject();
            StatusText.Text = $"Package created: {result["path"]?.GetValue<string>()}";
        }
        catch (Exception ex) { Error("Export Package", ex); }
    }

    private void OnLayerEditor(object sender, RoutedEventArgs e)
    {
        GeneratorNav.IsChecked = true;
        if (_pages["generator"] is GeneratorPage generator) generator.OpenWebLayerEditor();
    }

    private async void OnBlender(object sender, RoutedEventArgs e)
    {
        try
        {
            StatusText.Text = "Preparing Blender preview...";
            var result = (await _context.Bridge.CallAsync("blender_prepare", new { project = _context.Project.Snapshot() }))!.AsObject();
            var blender = result["blender"]?.GetValue<string>();
            if (string.IsNullOrWhiteSpace(blender)) throw new FileNotFoundException("Blender was not found.");
            var arguments = $"\"{result["model"]?.GetValue<string>()}\" --python \"{result["script"]?.GetValue<string>()}\" -- \"{result["color"]?.GetValue<string>()}\" \"{result["normal"]?.GetValue<string>()}\" 0.35 \"{result["settings"]?.GetValue<string>()}\"";
            Process.Start(new ProcessStartInfo(blender, arguments) { UseShellExecute = true });
            StatusText.Text = "Blender preview opened.";
        }
        catch (Exception ex) { Error("Blender Preview", ex); }
    }

    private bool ConfirmDiscard() => !_context.Project.IsDirty || MessageBox.Show("Discard unsaved project changes?", "NBA 2K Jersey Modder", MessageBoxButton.YesNo, MessageBoxImage.Question) == MessageBoxResult.Yes;
    private static void Error(string title, Exception ex) => MessageBox.Show(ex.Message, title, MessageBoxButton.OK, MessageBoxImage.Error);
    private async void OnClosing(object? sender, CancelEventArgs e) { if (!ConfirmDiscard()) { e.Cancel = true; return; } await _context.Bridge.DisposeAsync(); }
}

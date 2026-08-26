using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Markup;
using System.Windows.Threading;
using JerseyModder.Wpf.Controls;
using JerseyModder.Wpf.Models;
using JerseyModder.Wpf.Services;
using Microsoft.Win32;

namespace JerseyModder.Wpf.Views;

public sealed class LogoCreatorPage : ToolPageBase
{
    public sealed record StagedLogo(
        string Id, string Path, string ThumbnailPath, string Target, string TypeLabel)
    {
        public string FileName => System.IO.Path.GetFileName(Path);
        public override string ToString() => $"{TypeLabel}  |  {System.IO.Path.GetFileName(Path)}";
    }

    private readonly ImageViewport _reference = new(), _preview = new();
    private readonly TextBlock _sourceLabel = new()
    {
        Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"],
        Text = "No reference loaded.",
        TextWrapping = TextWrapping.Wrap,
    };
    private readonly TextBlock _stageSummary = new()
    {
        Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"],
        Text = "Selections made in the browser will appear here.",
        Margin = new Thickness(0, 7, 0, 0),
    };
    private readonly ListBox _stagedList = new();
    private readonly Button _reopenButton;
    private readonly LogoWebSessionService _webSession;
    private readonly DispatcherTimer _stateTimer;
    private List<StagedLogo> _staged = [];
    private string? _source;
    private long _lastStateWrite;
    private bool _readingState;
    private bool _returnHandled;

    public LogoCreatorPage(WorkspaceContext context) : base(context)
    {
        _webSession = new LogoWebSessionService(context.ProjectRoot);
        _stateTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(500) };
        _stateTimer.Tick += async (_, _) => await RefreshStateAsync();
        _stateTimer.Start();
        Application.Current.Exit += (_, _) => _webSession.Dispose();

        var body = new Grid();
        body.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        body.RowDefinitions.Add(new RowDefinition());
        var commandBar = new Grid { Margin = new Thickness(0, 0, 0, 12) };
        commandBar.ColumnDefinitions.Add(new ColumnDefinition());
        commandBar.ColumnDefinitions.Add(new ColumnDefinition());
        commandBar.ColumnDefinitions.Add(new ColumnDefinition());
        var upload = Ui.Button("Select Logos from Reference", OnOpen, true);
        upload.Margin = new Thickness(0, 0, 4, 0);
        var import = Ui.Button("Import Finished Logos", OnImport, true);
        import.Margin = new Thickness(4, 0, 4, 0);
        _reopenButton = Ui.Button("Reopen Logo Creator", (_, _) => ReopenWebEditor(), true);
        _reopenButton.Margin = new Thickness(4, 0, 0, 0);
        _reopenButton.IsEnabled = false;
        commandBar.Children.Add(upload);
        Grid.SetColumn(import, 1);
        commandBar.Children.Add(import);
        Grid.SetColumn(_reopenButton, 2);
        commandBar.Children.Add(_reopenButton);
        body.Children.Add(commandBar);

        var left = new StackPanel();
        _reference.Height = 175;
        left.Children.Add(new GroupBox { Header = "Reference", Content = _reference });
        _sourceLabel.Margin = new Thickness(2, 7, 2, 12);
        left.Children.Add(_sourceLabel);
        _preview.Height = 225;
        left.Children.Add(new GroupBox { Header = "Selected Logo", Content = _preview });
        left.Children.Add(Ui.Button("Open Web Logo Creator", (_, _) => ReopenWebEditor(), true));

        var right = new Grid();
        right.RowDefinitions.Add(new RowDefinition());
        right.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        right.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        _stagedList.ItemTemplate = BuildStageTemplate();
        _stagedList.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        _stagedList.SelectionChanged += async (_, _) => await ShowSelectedPreviewAsync();
        var stagedGroup = new GroupBox
        {
            Header = "Staged Logos",
            Content = _stagedList,
        };
        right.Children.Add(stagedGroup);
        Grid.SetRow(_stageSummary, 1);
        right.Children.Add(_stageSummary);
        var stageButtons = new Grid { Margin = new Thickness(0, 8, 0, 0) };
        stageButtons.ColumnDefinitions.Add(new ColumnDefinition());
        stageButtons.ColumnDefinitions.Add(new ColumnDefinition());
        stageButtons.ColumnDefinitions.Add(new ColumnDefinition());
        var edit = Ui.Button("Edit Staged Logos", (_, _) => OpenLogoEditor());
        var exportAi = Ui.Button("Export ChatGPT Logo Pack", ExportAiLogoPack);
        var send = Ui.Button("Send All to Generator", OnSend, true);
        edit.Margin = new Thickness(0, 0, 4, 0);
        exportAi.Margin = new Thickness(4, 0, 4, 0);
        send.Margin = new Thickness(4, 0, 0, 0);
        stageButtons.Children.Add(edit);
        Grid.SetColumn(exportAi, 1);
        stageButtons.Children.Add(exportAi);
        Grid.SetColumn(send, 2);
        stageButtons.Children.Add(send);
        Grid.SetRow(stageButtons, 2);
        right.Children.Add(stageButtons);

        var split = new Grid();
        split.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(300) });
        split.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(12) });
        split.ColumnDefinitions.Add(new ColumnDefinition());
        var leftScroll = new ScrollViewer
        {
            Content = left,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };
        split.Children.Add(leftScroll);
        Grid.SetColumn(right, 2);
        split.Children.Add(right);
        Grid.SetRow(split, 1);
        body.Children.Add(split);
        Content = Ui.Page(
            "Logo Creator",
            "Load one reference, select several logos in the browser, then review and send the staged set to the Generator.",
            body);
    }

    private static DataTemplate BuildStageTemplate() => (DataTemplate)XamlReader.Parse("""
        <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
          <Grid Margin="4" Height="64">
            <Grid.ColumnDefinitions>
              <ColumnDefinition Width="84" />
              <ColumnDefinition Width="*" />
            </Grid.ColumnDefinitions>
            <Border Background="#EEF1F4" BorderBrush="#CBD2DB" BorderThickness="1" CornerRadius="3" Padding="3">
              <Image Source="{Binding ThumbnailPath}" Stretch="Uniform" />
            </Border>
            <StackPanel Grid.Column="1" Margin="10,0,0,0" VerticalAlignment="Center">
              <TextBlock Text="{Binding TypeLabel}" FontWeight="SemiBold" FontSize="14" />
              <TextBlock Text="{Binding FileName}" Foreground="#667180" Margin="0,4,0,0" TextTrimming="CharacterEllipsis" />
            </StackPanel>
          </Grid>
        </DataTemplate>
        """);

    private async void OnOpen(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Choose a logo reference image",
            Filter = "Images|*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.gif|All files|*.*",
        };
        if (dialog.ShowDialog() != true) return;
        var originalPath = dialog.FileName;
        _sourceLabel.Text = $"Loading {Path.GetFileName(originalPath)}...";
        _staged = [];
        RefreshStagedList();
        try
        {
            _source = await StoreProjectReferenceAsync(
                originalPath,
                $"logo_{Path.GetFileNameWithoutExtension(originalPath)}");
            if (_source is null) return;
            var thumbnail = (await Context.Bridge.CallAsync("image_thumbnail", new
            {
                path = _source,
                maximumWidth = 1200,
                maximumHeight = 900,
            }))!.AsObject();
            _reference.Load(thumbnail["path"]?.GetValue<string>());
            _sourceLabel.Text = $"Reference: {Path.GetFileName(originalPath)}  |  " +
                $"{thumbnail["sourceWidth"]} x {thumbnail["sourceHeight"]}";
            Status("Starting web Logo Creator...");
            await _webSession.StartAsync(_source);
            _lastStateWrite = 0;
            _returnHandled = false;
            _reopenButton.IsEnabled = true;
            await RefreshStateAsync(true);
            Status("Web Logo Creator opened. Stage as many logos as you need from this reference.");
        }
        catch (Exception ex)
        {
            Error("Logo Creator", ex);
            _sourceLabel.Text = $"Could not open {Path.GetFileName(originalPath)}.";
        }
    }

    private async void OnImport(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Import finished logos for staging",
            Filter = "Images|*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.gif|All files|*.*",
            Multiselect = true,
        };
        if (dialog.ShowDialog() != true) return;
        try
        {
            var projectFile = await EnsureProjectFileAsync();
            if (projectFile is null) return;
            var firstSource = "";
            foreach (var sourcePath in dialog.FileNames)
            {
                var stored = ProjectWorkspace.StoreReference(
                    projectFile,
                    sourcePath,
                    $"logo_{Path.GetFileNameWithoutExtension(sourcePath)}");
                firstSource = string.IsNullOrEmpty(firstSource) ? stored : firstSource;
                await _webSession.ImportAsync(stored, "front_center_chest_logo");
            }
            _source ??= firstSource;
            _sourceLabel.Text = $"Imported {dialog.FileNames.Length} logo{(dialog.FileNames.Length == 1 ? "" : "s")} for staging.";
            var thumbnail = (await Context.Bridge.CallAsync("image_thumbnail", new
            {
                path = firstSource,
                maximumWidth = 1200,
                maximumHeight = 900,
            }))!.AsObject();
            _reference.Load(thumbnail["path"]?.GetValue<string>());
            _lastStateWrite = 0;
            _returnHandled = false;
            _reopenButton.IsEnabled = true;
            await RefreshStateAsync(true);
            _webSession.OpenEditor();
            Status($"Imported {dialog.FileNames.Length} logo(s) into staging. Set each logo type in the web editor.");
        }
        catch (Exception ex) { Error("Import Logos", ex); }
    }

    private void ReopenWebEditor()
    {
        try { _webSession.OpenBrowser(); }
        catch (Exception ex) { Error("Logo Creator", ex); }
    }

    private void OpenLogoEditor()
    {
        try { _webSession.OpenEditor(); }
        catch (Exception ex) { Error("Logo Editor", ex); }
    }

    private void ExportAiLogoPack(object sender, RoutedEventArgs e)
    {
        if (_staged.Count == 0)
        {
            MessageBox.Show("Stage one or more logos before exporting a ChatGPT pack.", "Logo Creator");
            return;
        }
        var dialog = new OpenFolderDialog
        {
            Title = "Choose where to create the ChatGPT logo pack",
            Multiselect = false,
        };
        if (dialog.ShowDialog() != true) return;
        try
        {
            var folder = NextPackFolder(dialog.FolderName);
            Directory.CreateDirectory(folder);
            var references = new List<string>();
            for (var index = 0; index < _staged.Count; index++)
            {
                var item = _staged[index];
                var name = $"{index + 1:00}_{SafeFileName(item.TypeLabel)}_reference.png";
                File.Copy(item.Path, Path.Combine(folder, name), true);
                references.Add($"{name}: {item.TypeLabel}");
            }
            File.WriteAllText(
                Path.Combine(folder, "chatgpt_logo_prompt.txt"),
                BuildAiLogoPrompt(references));
            Status($"Exported {_staged.Count} staged logo(s) to {folder}.");
            MessageBox.Show(
                $"Created a ChatGPT logo pack with {_staged.Count} reference image(s).\n\n{folder}",
                "Logo Pack Exported",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
        }
        catch (Exception ex) { Error("Export ChatGPT Logo Pack", ex); }
    }

    private static string NextPackFolder(string parent)
    {
        var basePath = Path.Combine(parent, "chatgpt_logo_pack");
        if (!Directory.Exists(basePath)) return basePath;
        for (var index = 2; ; index++)
        {
            var candidate = $"{basePath}_{index}";
            if (!Directory.Exists(candidate)) return candidate;
        }
    }

    private static string SafeFileName(string value)
    {
        var invalid = Path.GetInvalidFileNameChars();
        return new string(value.ToLowerInvariant().Select(character =>
            invalid.Contains(character) ? '_' : character == ' ' ? '_' : character).ToArray());
    }

    private static string BuildAiLogoPrompt(IEnumerable<string> references) => $"""
        Recreate every attached basketball uniform logo as a separate, polished, high-resolution PNG.

        Requirements:
        - Preserve the exact wording, design, colors, proportions, outline thickness, and intentional style of each reference.
        - Straighten photographed perspective, fabric curvature, accidental skew, uneven baselines, and wavy edges.
        - Preserve intentional arches, italics, curves, and asymmetry that belong to the original design.
        - Remove the jersey, background, wrinkles, compression artifacts, blur, and jagged edges.
        - Use a true transparent background with an alpha channel. Do not add white, black, gray, or checkerboard backgrounds.
        - Center each finished logo on a 2048 x 2048 transparent canvas with approximately 6 percent transparent padding.
        - Return one finished PNG for each reference, in the same numbered order.
        - Do not redesign the logos, change the text, add effects, or place them on a mockup.

        Reference order and intended logo types:
        {string.Join(Environment.NewLine, references)}
        """;

    private async Task RefreshStateAsync(bool force = false)
    {
        if (_readingState || string.IsNullOrWhiteSpace(_webSession.StatePath) ||
            !File.Exists(_webSession.StatePath)) return;
        var write = File.GetLastWriteTimeUtc(_webSession.StatePath).Ticks;
        if (!force && write == _lastStateWrite) return;
        _readingState = true;
        try
        {
            var root = JsonNode.Parse(await File.ReadAllTextAsync(_webSession.StatePath))?.AsObject();
            if (root is null) return;
            var selectedId = root["selectedId"]?.GetValue<string>();
            var returnRequested = root["returnRequested"]?.GetValue<bool>() == true;
            _staged = (root["items"] as JsonArray)?.Select(node =>
            {
                var item = node!.AsObject();
                return new StagedLogo(
                    item["id"]!.GetValue<string>(),
                    item["path"]!.GetValue<string>(),
                    item["thumbnailPath"]?.GetValue<string>() ?? item["path"]!.GetValue<string>(),
                    item["target"]!.GetValue<string>(),
                    item["typeLabel"]!.GetValue<string>());
            }).ToList() ?? [];
            _lastStateWrite = write;
            RefreshStagedList(selectedId);
            if (returnRequested && !_returnHandled)
            {
                _returnHandled = true;
                ReturnToApp();
            }
        }
        catch (IOException) { }
        catch (JsonException) { }
        finally { _readingState = false; }
    }

    private void ReturnToApp()
    {
        var window = Window.GetWindow(this) ?? Application.Current.MainWindow;
        if (window is null) return;
        if (window.WindowState == WindowState.Minimized) window.WindowState = WindowState.Normal;
        window.Show();
        window.Activate();
        window.Topmost = true;
        window.Topmost = false;
        window.Focus();
        Status($"Returned from web Logo Creator with {_staged.Count} staged logo(s).");
    }

    private void RefreshStagedList(string? selectedId = null)
    {
        var selected = selectedId is null
            ? _stagedList.SelectedItem as StagedLogo
            : _staged.FirstOrDefault(item => item.Id == selectedId);
        _stagedList.ItemsSource = null;
        _stagedList.ItemsSource = _staged;
        if (selected is not null)
            _stagedList.SelectedItem = _staged.FirstOrDefault(item => item.Id == selected.Id);
        else if (_staged.Count > 0)
            _stagedList.SelectedIndex = _staged.Count - 1;
        _stageSummary.Text = _staged.Count == 0
            ? "Selections made in the browser will appear here."
            : $"{_staged.Count} logo{(_staged.Count == 1 ? "" : "s")} staged and ready for the Generator.";
    }

    private async Task ShowSelectedPreviewAsync()
    {
        if (_stagedList.SelectedItem is not StagedLogo item || !File.Exists(item.Path)) return;
        try
        {
            var result = (await Context.Bridge.CallAsync("image_thumbnail", new
            {
                path = item.Path,
                maximumWidth = 900,
                maximumHeight = 650,
            }))!.AsObject();
            if (_stagedList.SelectedItem is StagedLogo current && current.Id == item.Id)
                _preview.Load(result["path"]?.GetValue<string>());
        }
        catch (Exception ex) { Status(ex.Message); }
    }

    private async void OnSend(object sender, RoutedEventArgs e)
    {
        if (_staged.Count == 0)
        {
            MessageBox.Show("Stage one or more logos in the web Logo Creator first.", "Logo Creator");
            return;
        }
        try
        {
            var projectFile = await EnsureProjectFileAsync();
            if (projectFile is null) return;
            var logos = (JsonArray)Context.Project.Generator["logos"]!;
            foreach (var item in _staged)
            {
                var storedPath = ProjectWorkspace.StoreAsset(projectFile, "logos", item.Path, item.TypeLabel);
                if (item.Target == "front_wordmark")
                {
                    Context.Project.SetImage("front_wordmark_image", storedPath);
                    continue;
                }
                logos.Add(new JsonObject
                {
                    { "path", storedPath }, { "targetName", item.Target },
                    { "typeLabel", item.TypeLabel },
                    { "offsetX", 0 }, { "offsetY", 0 }, { "scalePercent", 100 },
                    { "scaleWidthPercent", 100 }, { "scaleHeightPercent", 100 },
                    { "rotationDegrees", 0 },
                });
            }
            Context.Project.MarkChanged();
            await Context.Project.SaveAsync();
            Context.NotifyProjectPathChanged();
            Status($"Saved and sent {_staged.Count} staged logo(s) to Generator.");
        }
        catch (Exception ex) { Error("Send Logos to Generator", ex); }
    }
}

public sealed class TrimCreatorPage : ToolPageBase
{
    public sealed record StagedTrim(string Id, string Path, string ThumbnailPath, string Target, string TypeLabel)
    {
        public string FileName => System.IO.Path.GetFileName(Path);
    }

    private readonly ImageViewport _reference = new(), _preview = new();
    private readonly TextBlock _sourceLabel = new()
    {
        Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"],
        Text = "No mockup loaded.", TextWrapping = TextWrapping.Wrap,
    };
    private readonly TextBlock _summary = new()
    {
        Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"],
        Text = "Selections made in the browser will appear here.", Margin = new Thickness(0, 7, 0, 0),
    };
    private readonly ListBox _list = new();
    private readonly Button _reopen;
    private readonly TrimWebSessionService _web;
    private readonly DispatcherTimer _timer;
    private List<StagedTrim> _staged = [];
    private long _lastWrite;
    private bool _reading, _returnHandled;

    public TrimCreatorPage(WorkspaceContext context) : base(context)
    {
        _web = new TrimWebSessionService(context.ProjectRoot);
        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(500) };
        _timer.Tick += async (_, _) => await RefreshStateAsync();
        _timer.Start();
        Application.Current.Exit += (_, _) => _web.Dispose();

        var body = new Grid();
        body.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        body.RowDefinitions.Add(new RowDefinition());
        var commandBar = new Grid { Margin = new Thickness(0, 0, 0, 12) };
        commandBar.ColumnDefinitions.Add(new ColumnDefinition());
        commandBar.ColumnDefinitions.Add(new ColumnDefinition());
        commandBar.ColumnDefinitions.Add(new ColumnDefinition());
        var upload = Ui.Button("Select Trims from Mockup", OnOpen, true);
        upload.Margin = new Thickness(0, 0, 4, 0);
        var import = Ui.Button("Import Finished Trims", OnImport, true);
        import.Margin = new Thickness(4, 0, 4, 0);
        _reopen = Ui.Button("Reopen Trim Creator", (_, _) => OpenSelector(), true);
        _reopen.Margin = new Thickness(4, 0, 0, 0);
        _reopen.IsEnabled = false;
        commandBar.Children.Add(upload);
        Grid.SetColumn(import, 1); commandBar.Children.Add(import);
        Grid.SetColumn(_reopen, 2); commandBar.Children.Add(_reopen);
        body.Children.Add(commandBar);

        var left = new StackPanel();
        _reference.Height = 175;
        left.Children.Add(new GroupBox { Header = "Mockup", Content = _reference });
        _sourceLabel.Margin = new Thickness(2, 7, 2, 12); left.Children.Add(_sourceLabel);
        _preview.Height = 225;
        left.Children.Add(new GroupBox { Header = "Selected Trim", Content = _preview });
        left.Children.Add(Ui.Button("Open Web Trim Selector", (_, _) => OpenSelector(), true));

        var right = new Grid();
        right.RowDefinitions.Add(new RowDefinition());
        right.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        right.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        _list.ItemTemplate = BuildTrimTemplate();
        _list.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        _list.SelectionChanged += async (_, _) => await ShowSelectedAsync();
        right.Children.Add(new GroupBox { Header = "Staged Trims", Content = _list });
        Grid.SetRow(_summary, 1); right.Children.Add(_summary);
        var actions = new Grid { Margin = new Thickness(0, 8, 0, 0) };
        for (var index = 0; index < 3; index++) actions.ColumnDefinitions.Add(new ColumnDefinition());
        var edit = Ui.Button("Edit Staged Trims", (_, _) => OpenEditor());
        var export = Ui.Button("Export ChatGPT Trim Pack", ExportAiPack);
        var send = Ui.Button("Send All to Generator", OnSend, true);
        edit.Margin = new Thickness(0, 0, 4, 0); export.Margin = new Thickness(4); send.Margin = new Thickness(4, 0, 0, 0);
        actions.Children.Add(edit); Grid.SetColumn(export, 1); actions.Children.Add(export); Grid.SetColumn(send, 2); actions.Children.Add(send);
        Grid.SetRow(actions, 2); right.Children.Add(actions);

        var split = new Grid();
        split.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(300) });
        split.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(12) });
        split.ColumnDefinitions.Add(new ColumnDefinition());
        split.Children.Add(new ScrollViewer { Content = left, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
        Grid.SetColumn(right, 2); split.Children.Add(right); Grid.SetRow(split, 1); body.Children.Add(split);
        Content = Ui.Page("Trim Creator", "Load one mockup, select several trim lines in the browser, then review and send the staged set to the Generator.", body);
    }

    private static DataTemplate BuildTrimTemplate() => (DataTemplate)XamlReader.Parse("""
        <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
          <Grid Margin="4" Height="64"><Grid.ColumnDefinitions><ColumnDefinition Width="110"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
            <Border Background="#EEF1F4" BorderBrush="#CBD2DB" BorderThickness="1" CornerRadius="3" Padding="3"><Image Source="{Binding ThumbnailPath}" Stretch="Uniform"/></Border>
            <StackPanel Grid.Column="1" Margin="10,0,0,0" VerticalAlignment="Center"><TextBlock Text="{Binding TypeLabel}" FontWeight="SemiBold" FontSize="14"/><TextBlock Text="{Binding FileName}" Foreground="#667180" Margin="0,4,0,0" TextTrimming="CharacterEllipsis"/></StackPanel>
          </Grid>
        </DataTemplate>
        """);

    private async void OnOpen(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog { Title = "Choose a uniform mockup", Filter = "Images|*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.gif|All files|*.*" };
        if (dialog.ShowDialog() != true) return;
        var originalPath = dialog.FileName;
        _staged = []; RefreshList(); _sourceLabel.Text = $"Loading {Path.GetFileName(originalPath)}...";
        try
        {
            var source = await StoreProjectReferenceAsync(
                originalPath,
                $"trim_{Path.GetFileNameWithoutExtension(originalPath)}");
            if (source is null) return;
            var thumbnail = (await Context.Bridge.CallAsync("image_thumbnail", new { path = source, maximumWidth = 1200, maximumHeight = 900 }))!.AsObject();
            _reference.Load(thumbnail["path"]?.GetValue<string>());
            _sourceLabel.Text = $"Mockup: {Path.GetFileName(originalPath)}  |  {thumbnail["sourceWidth"]} x {thumbnail["sourceHeight"]}";
            Status("Starting web Trim Selector..."); await _web.StartAsync(source);
            _lastWrite = 0; _returnHandled = false; _reopen.IsEnabled = true;
            await RefreshStateAsync(true); Status("Web Trim Selector opened. Stage as many trims as you need from this mockup.");
        }
        catch (Exception ex) { Error("Trim Creator", ex); }
    }

    private async void OnImport(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Import finished trims for staging",
            Filter = "Images|*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.gif|All files|*.*",
            Multiselect = true,
        };
        if (dialog.ShowDialog() != true) return;
        try
        {
            var projectFile = await EnsureProjectFileAsync();
            if (projectFile is null) return;
            var firstSource = "";
            foreach (var sourcePath in dialog.FileNames)
            {
                var stored = ProjectWorkspace.StoreReference(
                    projectFile,
                    sourcePath,
                    $"trim_{Path.GetFileNameWithoutExtension(sourcePath)}");
                firstSource = string.IsNullOrEmpty(firstSource) ? stored : firstSource;
                await _web.ImportAsync(stored, "collar_trim_image");
            }
            _sourceLabel.Text = $"Imported {dialog.FileNames.Length} trim{(dialog.FileNames.Length == 1 ? "" : "s")} for staging.";
            var thumbnail = (await Context.Bridge.CallAsync("image_thumbnail", new
            {
                path = firstSource,
                maximumWidth = 1200,
                maximumHeight = 900,
            }))!.AsObject();
            _reference.Load(thumbnail["path"]?.GetValue<string>());
            _lastWrite = 0;
            _returnHandled = false;
            _reopen.IsEnabled = true;
            await RefreshStateAsync(true);
            _web.OpenEditor();
            Status($"Imported {dialog.FileNames.Length} trim(s) into staging. Set each trim type in the web editor.");
        }
        catch (Exception ex) { Error("Import Trims", ex); }
    }

    private void OpenSelector() { try { _web.OpenSelector(); } catch (Exception ex) { Error("Trim Selector", ex); } }
    private void OpenEditor() { try { _web.OpenEditor(); } catch (Exception ex) { Error("Trim Editor", ex); } }

    private async Task RefreshStateAsync(bool force = false)
    {
        if (_reading || string.IsNullOrWhiteSpace(_web.StatePath) || !File.Exists(_web.StatePath)) return;
        var write = File.GetLastWriteTimeUtc(_web.StatePath).Ticks;
        if (!force && write == _lastWrite) return;
        _reading = true;
        try
        {
            var root = JsonNode.Parse(await File.ReadAllTextAsync(_web.StatePath))?.AsObject(); if (root is null) return;
            var selectedId = root["selectedId"]?.GetValue<string>();
            _staged = (root["items"] as JsonArray)?.Select(node => { var item = node!.AsObject(); return new StagedTrim(item["id"]!.GetValue<string>(), item["path"]!.GetValue<string>(), item["thumbnailPath"]!.GetValue<string>(), item["target"]!.GetValue<string>(), item["typeLabel"]!.GetValue<string>()); }).ToList() ?? [];
            _lastWrite = write; RefreshList(selectedId);
            if (root["returnRequested"]?.GetValue<bool>() == true && !_returnHandled) { _returnHandled = true; ReturnToApp(); }
        }
        catch (IOException) { } catch (JsonException) { } finally { _reading = false; }
    }

    private void RefreshList(string? selectedId = null)
    {
        var selected = selectedId is null ? _list.SelectedItem as StagedTrim : _staged.FirstOrDefault(item => item.Id == selectedId);
        _list.ItemsSource = null; _list.ItemsSource = _staged;
        if (selected is not null) _list.SelectedItem = _staged.FirstOrDefault(item => item.Id == selected.Id); else if (_staged.Count > 0) _list.SelectedIndex = _staged.Count - 1;
        _summary.Text = _staged.Count == 0 ? "Selections made in the browser will appear here." : $"{_staged.Count} trim{(_staged.Count == 1 ? "" : "s")} staged and ready for the Generator.";
    }

    private async Task ShowSelectedAsync()
    {
        if (_list.SelectedItem is not StagedTrim item || !File.Exists(item.Path)) return;
        try { var result = (await Context.Bridge.CallAsync("image_thumbnail", new { path = item.Path, maximumWidth = 1100, maximumHeight = 500 }))!.AsObject(); if (_list.SelectedItem is StagedTrim current && current.Id == item.Id) _preview.Load(result["path"]?.GetValue<string>()); }
        catch (Exception ex) { Status(ex.Message); }
    }

    private void ReturnToApp()
    {
        var window = Window.GetWindow(this) ?? Application.Current.MainWindow; if (window is null) return;
        if (window.WindowState == WindowState.Minimized) window.WindowState = WindowState.Normal;
        window.Show(); window.Activate(); window.Topmost = true; window.Topmost = false; window.Focus();
        Status($"Returned from web Trim Creator with {_staged.Count} staged trim(s).");
    }

    private async void OnSend(object sender, RoutedEventArgs e)
    {
        if (_staged.Count == 0) { MessageBox.Show("Stage one or more trims in the web Trim Selector first.", "Trim Creator"); return; }
        try
        {
            var projectFile = await EnsureProjectFileAsync();
            if (projectFile is null) return;
            foreach (var item in _staged)
            {
                var storedPath = ProjectWorkspace.StoreAsset(projectFile, "trims", item.Path, item.TypeLabel);
                Context.Project.SetImage(item.Target, storedPath);
            }
            await Context.Project.SaveAsync();
            Context.NotifyProjectPathChanged();
            Status($"Saved and sent {_staged.Count} staged trim(s) to Generator.");
        }
        catch (Exception ex) { Error("Send Trims to Generator", ex); }
    }

    private void ExportAiPack(object sender, RoutedEventArgs e)
    {
        if (_staged.Count == 0) { MessageBox.Show("Stage one or more trims before exporting a ChatGPT pack.", "Trim Creator"); return; }
        var dialog = new OpenFolderDialog { Title = "Choose where to create the ChatGPT trim pack", Multiselect = false }; if (dialog.ShowDialog() != true) return;
        try
        {
            var folder = NextFolder(dialog.FolderName); Directory.CreateDirectory(folder); var references = new List<string>();
            for (var index = 0; index < _staged.Count; index++) { var item = _staged[index]; var name = $"{index + 1:00}_{SafeName(item.TypeLabel)}_reference.png"; File.Copy(item.Path, Path.Combine(folder, name), true); references.Add($"{name}: {item.TypeLabel}"); }
            File.WriteAllText(Path.Combine(folder, "chatgpt_trim_prompt.txt"), BuildPrompt(references));
            Status($"Exported {_staged.Count} staged trim(s) to {folder}."); MessageBox.Show($"Created a ChatGPT trim pack with {_staged.Count} reference image(s).\n\n{folder}", "Trim Pack Exported");
        }
        catch (Exception ex) { Error("Export ChatGPT Trim Pack", ex); }
    }

    private static string NextFolder(string parent) { var root = Path.Combine(parent, "chatgpt_trim_pack"); if (!Directory.Exists(root)) return root; for (var index = 2; ; index++) { var candidate = $"{root}_{index}"; if (!Directory.Exists(candidate)) return candidate; } }
    private static string SafeName(string value) { var invalid = Path.GetInvalidFileNameChars(); return new string(value.ToLowerInvariant().Select(character => invalid.Contains(character) ? '_' : character == ' ' ? '_' : character).ToArray()); }
    private static string BuildPrompt(IEnumerable<string> references) => $"""
        Recreate every attached basketball uniform trim as a separate, polished, high-resolution transparent PNG.
        Keep each design as a perfectly straight horizontal strip. Preserve the exact stripe order, relative stripe thickness, colors, outlines, and intentional texture. Even out gaps, wavy edges, blur, and compression artifacts without changing the design. Make the strip tileable left-to-right. Use a true transparent alpha background and do not place the trim on a uniform mockup. Return one PNG per reference in the same numbered order.

        Reference order and trim types:
        {string.Join(Environment.NewLine, references)}
        """;
}

public sealed class TrimPathPage : ToolPageBase
{
    private sealed record TrimSource(string Path)
    {
        public string Name => System.IO.Path.GetFileName(Path);
        public override string ToString() => Name;
    }

    private sealed record PathLayer(int StoredIndex, string Name, string FileName)
    {
        public override string ToString() => $"{Name}  |  {FileName}";
    }

    private readonly ImageViewport _patternPreview = new();
    private readonly ComboBox _sources = new();
    private readonly ListBox _layers = new();
    private readonly TextBlock _sourceStatus = new()
    {
        Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"],
        Text = "Choose a transparent trim strip to begin.",
        TextWrapping = TextWrapping.Wrap,
    };
    private readonly TextBlock _layerStatus = new()
    {
        Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"],
        TextWrapping = TextWrapping.Wrap,
        Margin = new Thickness(0, 8, 0, 0),
    };
    private readonly Button _openButton;
    private readonly Button _reopenButton;
    private readonly TrimPathLabWebSessionService _web;
    private readonly DispatcherTimer _stateTimer = new() { Interval = TimeSpan.FromMilliseconds(400) };
    private DateTime _lastStateWrite;
    private bool _returnHandled;
    private bool _applyingWebState;
    private bool _refreshingSources;
    private string? _patternPath;

    public TrimPathPage(WorkspaceContext context) : base(context)
    {
        _web = new TrimPathLabWebSessionService(context.ProjectRoot);
        _stateTimer.Tick += async (_, _) => await RefreshWebStateAsync();
        _stateTimer.Start();
        Application.Current.Exit += (_, _) => _web.Dispose();

        var root = new Grid();
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition());

        var commandBar = new Grid { Margin = new Thickness(0, 0, 0, 12) };
        commandBar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(2, GridUnitType.Star) });
        commandBar.ColumnDefinitions.Add(new ColumnDefinition());
        _openButton = Ui.Button("Open Web Trim Path Lab", async (_, _) => await OpenLabAsync(), true);
        _openButton.MinHeight = 44;
        _openButton.Margin = new Thickness(0, 0, 5, 0);
        _reopenButton = Ui.Button("Reopen Lab", (_, _) => ReopenLab(), true);
        _reopenButton.MinHeight = 44;
        _reopenButton.Margin = new Thickness(5, 0, 0, 0);
        _reopenButton.IsEnabled = false;
        commandBar.Children.Add(_openButton);
        Grid.SetColumn(_reopenButton, 1);
        commandBar.Children.Add(_reopenButton);
        root.Children.Add(commandBar);

        var left = new StackPanel();
        _sources.SelectionChanged += (_, _) => SelectSource();
        left.Children.Add(Ui.Row("Trim source", _sources));
        left.Children.Add(Ui.Button("Import Trim Source", OnImportSource));
        _patternPreview.Height = 250;
        left.Children.Add(new GroupBox
        {
            Header = "Selected Trim Pattern",
            Content = _patternPreview,
            Margin = new Thickness(0, 12, 0, 0),
        });
        _sourceStatus.Margin = new Thickness(2, 8, 2, 0);
        left.Children.Add(_sourceStatus);

        var right = new Grid();
        right.RowDefinitions.Add(new RowDefinition());
        right.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        right.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        _layers.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        right.Children.Add(new GroupBox { Header = "Current Generator Trim Paths", Content = _layers });
        Grid.SetRow(_layerStatus, 1);
        right.Children.Add(_layerStatus);
        var actions = new Grid { Margin = new Thickness(0, 10, 0, 0) };
        actions.ColumnDefinitions.Add(new ColumnDefinition());
        actions.ColumnDefinitions.Add(new ColumnDefinition());
        var remove = Ui.Button("Remove Selected Layer", OnRemoveLayer);
        remove.Margin = new Thickness(0, 0, 5, 0);
        var clear = Ui.Button("Clear Current Template", OnClearScope);
        clear.Margin = new Thickness(5, 0, 0, 0);
        actions.Children.Add(remove);
        Grid.SetColumn(clear, 1);
        actions.Children.Add(clear);
        Grid.SetRow(actions, 2);
        right.Children.Add(actions);

        var split = new Grid();
        split.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(340) });
        split.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(14) });
        split.ColumnDefinitions.Add(new ColumnDefinition());
        split.Children.Add(new ScrollViewer { Content = left, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
        Grid.SetColumn(right, 2);
        split.Children.Add(right);
        Grid.SetRow(split, 1);
        root.Children.Add(split);

        Content = Ui.Page(
            "Trim Path Lab",
            "Choose a trim strip, then draw straight, curved, mirrored, or T-shaped paths over the actual Generator preview in the browser.",
            root);
        Loaded += (_, _) =>
        {
            SubscribeToCurrentProject();
            RefreshSources();
            RefreshLayers();
        };
    }

    protected override void OnProjectReplaced()
    {
        _web.Stop();
        _reopenButton.IsEnabled = false;
        SubscribeToCurrentProject();
        RefreshSources();
        RefreshLayers();
    }

    private ProjectStore? _subscribedProject;
    private void SubscribeToCurrentProject()
    {
        if (ReferenceEquals(_subscribedProject, Context.Project)) return;
        if (_subscribedProject is not null) _subscribedProject.Changed -= OnProjectChanged;
        _subscribedProject = Context.Project;
        _subscribedProject.Changed += OnProjectChanged;
    }

    private void OnProjectChanged(object? sender, EventArgs e) => Dispatcher.Invoke(() =>
    {
        if (!_applyingWebState && _web.Url is not null)
        {
            _web.Stop();
            _reopenButton.IsEnabled = false;
        }
        RefreshSources();
        RefreshLayers();
    });

    private void RefreshSources(string? selectPath = null)
    {
        _refreshingSources = true;
        var candidates = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        void Add(string? path) { if (!string.IsNullOrWhiteSpace(path) && File.Exists(path)) candidates.Add(Path.GetFullPath(path)); }

        foreach (var key in new[] { "collar_trim_image", "left_arm_hole_trim_image", "right_arm_hole_trim_image", "waistband_image" })
            Add(Context.Project.GetImage(key));
        if (Context.Project.FilePath is { } projectFile)
        {
            var folder = Path.Combine(Path.GetDirectoryName(projectFile)!, "assets", "trims");
            if (Directory.Exists(folder))
            {
                var pathOutputFolder = Path.Combine(folder, "paths") + Path.DirectorySeparatorChar;
                foreach (var path in Directory.EnumerateFiles(folder, "*.*", SearchOption.AllDirectories)
                    .Where(path => !Path.GetFullPath(path).StartsWith(pathOutputFolder, StringComparison.OrdinalIgnoreCase))
                    .Where(path => new[] { ".png", ".jpg", ".jpeg" }.Contains(Path.GetExtension(path), StringComparer.OrdinalIgnoreCase)))
                    Add(path);
            }
        }
        Add(_patternPath);
        var sources = candidates.OrderBy(path => Path.GetFileName(path), StringComparer.OrdinalIgnoreCase).Select(path => new TrimSource(path)).ToList();
        var wanted = selectPath ?? _patternPath;
        _sources.ItemsSource = sources;
        _sources.SelectedItem = sources.FirstOrDefault(item => string.Equals(item.Path, wanted, StringComparison.OrdinalIgnoreCase));
        if (_sources.SelectedItem is null && sources.Count > 0) _sources.SelectedIndex = 0;
        _refreshingSources = false;
        if (_sources.SelectedItem is TrimSource selected)
        {
            _patternPath = selected.Path;
            _patternPreview.Load(selected.Path);
            _sourceStatus.Text = $"Using {selected.Name}. The browser keeps its original pixels while wrapping it along each path.";
        }
        if (sources.Count == 0)
        {
            _patternPath = null;
            _sourceStatus.Text = "Import or send a transparent trim PNG from Trim Creator first.";
        }
    }

    private void SelectSource()
    {
        if (_refreshingSources) return;
        if (_sources.SelectedItem is not TrimSource source) return;
        _patternPath = source.Path;
        _patternPreview.Load(source.Path);
        _sourceStatus.Text = $"Using {source.Name}. The browser keeps its original pixels while wrapping it along each path.";
        if (_web.Url is not null)
        {
            _web.Stop();
            _reopenButton.IsEnabled = false;
        }
    }

    private async void OnImportSource(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Import a transparent trim strip",
            Filter = "Trim images|*.png;*.jpg;*.jpeg|All files|*.*",
            Multiselect = false,
            InitialDirectory = Context.Project.FilePath is { } file
                ? Path.Combine(Path.GetDirectoryName(file)!, "assets", "trims")
                : ProjectWorkspace.DefaultProjectsFolder,
        };
        if (dialog.ShowDialog() != true) return;
        try
        {
            var stored = await StoreProjectAssetAsync("trims", dialog.FileName, "trim_path_source");
            if (stored is null) return;
            _patternPath = stored;
            RefreshSources(stored);
            Status($"Imported trim source {Path.GetFileName(stored)}.");
        }
        catch (Exception ex) { Error("Import Trim Source", ex); }
    }

    private async Task OpenLabAsync()
    {
        if (string.IsNullOrWhiteSpace(_patternPath) || !File.Exists(_patternPath))
        {
            MessageBox.Show("Choose or import a trim source first.", "Trim Path Lab");
            return;
        }
        try
        {
            var projectFile = await EnsureProjectFileAsync();
            if (projectFile is null) return;
            Status("Opening web Trim Path Lab...");
            await _web.StartAsync(
                Context.Project.Snapshot(),
                _patternPath,
                Path.GetDirectoryName(projectFile)!);
            _lastStateWrite = _web.StatePath is not null && File.Exists(_web.StatePath)
                ? File.GetLastWriteTimeUtc(_web.StatePath) : default;
            _returnHandled = false;
            _reopenButton.IsEnabled = true;
            Status("Web Trim Path Lab opened. Send layers to the Generator when the path set is ready.");
        }
        catch (Exception ex) { Error("Web Trim Path Lab", ex); }
    }

    private void ReopenLab()
    {
        try { _web.OpenBrowser(); }
        catch (Exception ex) { Error("Web Trim Path Lab", ex); }
    }

    private async Task RefreshWebStateAsync()
    {
        var path = _web.StatePath;
        if (path is null || !File.Exists(path)) return;
        var write = File.GetLastWriteTimeUtc(path);
        if (write <= _lastStateWrite) return;
        try
        {
            var root = JsonNode.Parse(await File.ReadAllTextAsync(path))?.AsObject();
            var project = root?["project"]?.AsObject();
            if (project is null) return;
            _lastStateWrite = write;
            if (project.ToJsonString() != Context.Project.Snapshot().ToJsonString())
            {
                _applyingWebState = true;
                try
                {
                    Context.Project.ApplyExternal((JsonObject)project.DeepClone());
                    if (Context.Project.FilePath is not null) await Context.Project.SaveAsync();
                }
                finally { _applyingWebState = false; }
                RefreshLayers();
            }
            if (root?["returnRequested"]?.GetValue<bool>() == true && !_returnHandled)
            {
                _returnHandled = true;
                var window = Window.GetWindow(this) ?? Application.Current.MainWindow;
                if (window is not null)
                {
                    if (window.WindowState == WindowState.Minimized) window.WindowState = WindowState.Normal;
                    window.Show();
                    window.Activate();
                    window.Topmost = true;
                    window.Topmost = false;
                    window.Focus();
                }
                Status("Returned from the web Trim Path Lab.");
            }
        }
        catch (IOException) { }
        catch (JsonException) { }
    }

    private void RefreshLayers()
    {
        var array = Context.Project.Generator["trimPathLayers"] as JsonArray;
        var active = new List<PathLayer>();
        if (array is not null)
        {
            for (var index = 0; index < array.Count; index++)
            {
                if (array[index] is not JsonObject item) continue;
                var garment = item["garment"]?.GetValue<string>() ?? "Shorts";
                var template = item["templateName"]?.GetValue<string>() ?? Context.Project.TemplateName;
                if (garment != Context.Project.Garment || template != Context.Project.TemplateName) continue;
                var name = item["name"]?.GetValue<string>() ?? $"Trim Path {active.Count + 1}";
                var fileName = Path.GetFileName(item["path"]?.GetValue<string>() ?? "");
                active.Add(new PathLayer(index, name, fileName));
            }
        }
        _layers.ItemsSource = active;
        _layerStatus.Text = active.Count == 0
            ? $"No paths are assigned to {Context.Project.Garment} - {Context.Project.TemplateName}."
            : $"{active.Count} independent path layer{(active.Count == 1 ? "" : "s")} assigned to {Context.Project.Garment} - {Context.Project.TemplateName}. Reposition them in the Generator web editor.";
    }

    private void OnRemoveLayer(object sender, RoutedEventArgs e)
    {
        if (_layers.SelectedItem is not PathLayer selected) return;
        (Context.Project.Generator["trimPathLayers"] as JsonArray)?.RemoveAt(selected.StoredIndex);
        Context.Project.MarkChanged();
        RefreshLayers();
    }

    private void OnClearScope(object sender, RoutedEventArgs e)
    {
        var array = Context.Project.Generator["trimPathLayers"] as JsonArray;
        if (array is null) return;
        for (var index = array.Count - 1; index >= 0; index--)
        {
            if (array[index] is not JsonObject item) continue;
            var garment = item["garment"]?.GetValue<string>() ?? "Shorts";
            var template = item["templateName"]?.GetValue<string>() ?? Context.Project.TemplateName;
            if (garment == Context.Project.Garment && template == Context.Project.TemplateName) array.RemoveAt(index);
        }
        Context.Project.MarkChanged();
        RefreshLayers();
    }
}

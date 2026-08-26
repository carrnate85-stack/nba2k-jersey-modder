using System.Windows;
using System.Windows.Controls;
using JerseyModder.Wpf.Models;
using JerseyModder.Wpf.Services;

namespace JerseyModder.Wpf.Views;

public abstract class ToolPageBase : UserControl
{
    protected WorkspaceContext Context { get; }

    protected ToolPageBase(WorkspaceContext context)
    {
        Context = context;
        context.ProjectReplaced += (_, _) => OnProjectReplaced();
    }

    protected virtual void OnProjectReplaced() { }
    protected void Status(string message) => Context.SetStatus(message);
    protected static void Error(string title, Exception exception) =>
        MessageBox.Show(exception.Message, title, MessageBoxButton.OK, MessageBoxImage.Error);

    protected async Task<string?> EnsureProjectFileAsync()
    {
        if (Context.Project.FilePath is not null) return Context.Project.FilePath;
        var dialog = new NewProjectDialog { Owner = Window.GetWindow(this) ?? Application.Current.MainWindow };
        if (dialog.ShowDialog() != true) return null;
        var path = ProjectWorkspace.Create(dialog.ParentFolder, dialog.ProjectName);
        await Context.Project.SaveAsync(path);
        Context.NotifyProjectPathChanged();
        return path;
    }

    protected async Task<string?> StoreProjectAssetAsync(string category, string sourcePath, string label)
    {
        var projectFile = await EnsureProjectFileAsync();
        return projectFile is null ? null : ProjectWorkspace.StoreAsset(projectFile, category, sourcePath, label);
    }

    protected static Grid Header(string title, string description)
    {
        var grid = new Grid { Margin = new Thickness(0, 0, 0, 14) };
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        var heading = new TextBlock { Text = title, FontSize = 24, FontWeight = FontWeights.SemiBold };
        var copy = new TextBlock { Text = description, Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"], Margin = new Thickness(0, 4, 0, 0) };
        Grid.SetRow(copy, 1); grid.Children.Add(heading); grid.Children.Add(copy); return grid;
    }
}

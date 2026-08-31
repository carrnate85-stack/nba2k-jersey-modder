using System.IO;
using System.Windows;
using System.Windows.Controls;
using JerseyModder.Wpf.Services;

namespace JerseyModder.Wpf.Views;

public partial class NewProjectDialog : Window
{
    public string ProjectName => ProjectNameBox.Text.Trim();
    public string ParentFolder => ParentFolderBox.Text;

    public NewProjectDialog()
    {
        InitializeComponent();
        ParentFolderBox.Text = ProjectWorkspace.DefaultProjectsFolder;
        ProjectNameBox.TextChanged += (_, _) => UpdatePreview();
        ParentFolderBox.TextChanged += (_, _) => UpdatePreview();
        Loaded += (_, _) => { ProjectNameBox.Focus(); ProjectNameBox.SelectAll(); UpdatePreview(); };
    }

    private void OnCreate(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(ProjectName))
        {
            MessageBox.Show("Choose a project name.", "Create Project", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        try
        {
            Directory.CreateDirectory(ParentFolder);
        }
        catch (Exception ex)
        {
            MessageBox.Show($"The selected project folder could not be created.\n\n{ex.Message}", "Create Project", MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }
        DialogResult = true;
    }

    private void UpdatePreview() => FolderPreview.Text = Path.Combine(ParentFolder, ProjectWorkspace.SafeName(ProjectName));
    private void OnSelectAll(object sender, RoutedEventArgs e) { if (sender is TextBox box) box.SelectAll(); }
}

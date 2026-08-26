using System.IO;
using System.Windows;
using System.Windows.Controls;
using JerseyModder.Wpf.Services;
using Microsoft.Win32;

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

    private void OnBrowse(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFolderDialog { Title = "Choose where the project folder will be created", Multiselect = false, InitialDirectory = ParentFolder };
        if (dialog.ShowDialog(this) == true) ParentFolderBox.Text = dialog.FolderName;
    }

    private void OnCreate(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(ProjectName) || string.IsNullOrWhiteSpace(ParentFolder))
        {
            MessageBox.Show("Choose a project name and location.", "Create Project", MessageBoxButton.OK, MessageBoxImage.Information);
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

using JerseyModder.Wpf.Models;

namespace JerseyModder.Wpf.Services;

public sealed class WorkspaceContext
{
    public ProjectStore Project { get; private set; } = new();
    public PythonBridge Bridge { get; }
    public string ProjectRoot { get; }
    public event EventHandler<string>? StatusChanged;
    public event EventHandler? ProjectReplaced;
    public event EventHandler? ProjectPathChanged;

    public WorkspaceContext(string projectRoot)
    {
        ProjectRoot = projectRoot;
        Bridge = new PythonBridge(projectRoot);
    }

    public void ReplaceProject(ProjectStore project)
    {
        Project = project;
        ProjectReplaced?.Invoke(this, EventArgs.Empty);
    }

    public void SetStatus(string message) => StatusChanged?.Invoke(this, message);
    public void NotifyProjectPathChanged() => ProjectPathChanged?.Invoke(this, EventArgs.Empty);
}

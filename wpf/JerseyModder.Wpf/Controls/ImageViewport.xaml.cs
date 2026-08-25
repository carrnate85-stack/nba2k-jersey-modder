using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media.Imaging;
using JerseyModder.Wpf.Services;

namespace JerseyModder.Wpf.Controls;

public partial class ImageViewport : UserControl
{
    private Point? _panStart;
    private double _horizontalStart;
    private double _verticalStart;
    private double _zoom = 1;

    public event EventHandler<Point>? ImagePointClicked;
    public event EventHandler? ImageRightClicked;
    public BitmapSource? Source => Picture.Source as BitmapSource;

    public ImageViewport() => InitializeComponent();

    public void Load(string? path)
    {
        Picture.Source = WpfImage.Load(path);
        EmptyState.Visibility = Picture.Source is null ? Visibility.Visible : Visibility.Collapsed;
        Dispatcher.BeginInvoke(Fit, System.Windows.Threading.DispatcherPriority.Loaded);
    }

    public void Fit()
    {
        if (Picture.Source is BitmapSource source)
        {
            var availableWidth = Math.Max(1, ActualWidth - 22);
            var availableHeight = Math.Max(1, ActualHeight - 22);
            var scale = Math.Min(availableWidth / source.PixelWidth, availableHeight / source.PixelHeight);
            Picture.Width = Math.Max(1, source.PixelWidth * scale);
            Picture.Height = Math.Max(1, source.PixelHeight * scale);
        }
        _zoom = 1;
        ZoomTransform.ScaleX = ZoomTransform.ScaleY = _zoom;
        ZoomLabel.Text = "100%";
        Scroller.ScrollToHome();
    }

    private void OnSizeChanged(object sender, SizeChangedEventArgs e)
    {
        if (_zoom == 1 && Picture.Source is not null) Fit();
    }

    private void OnMouseWheel(object sender, MouseWheelEventArgs e)
    {
        _zoom = Math.Clamp(_zoom * (e.Delta > 0 ? 1.12 : 0.89), .2, 8);
        ZoomTransform.ScaleX = ZoomTransform.ScaleY = _zoom;
        ZoomLabel.Text = $"{_zoom * 100:0}%";
        e.Handled = true;
    }

    private void OnMouseDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Middle) return;
        _panStart = e.GetPosition(this);
        _horizontalStart = Scroller.HorizontalOffset;
        _verticalStart = Scroller.VerticalOffset;
        CaptureMouse();
        Cursor = Cursors.ScrollAll;
        e.Handled = true;
    }

    private void OnMouseMove(object sender, MouseEventArgs e)
    {
        if (_panStart is not Point start || e.MiddleButton != MouseButtonState.Pressed) return;
        var current = e.GetPosition(this);
        Scroller.ScrollToHorizontalOffset(_horizontalStart + start.X - current.X);
        Scroller.ScrollToVerticalOffset(_verticalStart + start.Y - current.Y);
    }

    private void OnMouseUp(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Middle) return;
        _panStart = null;
        ReleaseMouseCapture();
        Cursor = Cursors.Arrow;
        e.Handled = true;
    }

    private void OnImageClick(object sender, MouseButtonEventArgs e)
    {
        if (Picture.Source is not BitmapSource source) return;
        var point = e.GetPosition(Picture);
        if (Picture.ActualWidth <= 0 || Picture.ActualHeight <= 0) return;
        ImagePointClicked?.Invoke(this, new Point(
            Math.Clamp(point.X / Picture.ActualWidth * source.PixelWidth, 0, source.PixelWidth),
            Math.Clamp(point.Y / Picture.ActualHeight * source.PixelHeight, 0, source.PixelHeight)));
    }

    private void OnImageRightClick(object sender, MouseButtonEventArgs e)
    {
        ImageRightClicked?.Invoke(this, EventArgs.Empty);
        e.Handled = true;
    }
}

using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using FlaUI.Core.AutomationElements;
using FlaUI.UIA3;

internal static class NativeAutomationServer
{
    public static int Run(string[] args)
    {
        try
        {
            var options = NativeAutomationServerOptions.Parse(args);
            using var automation = new UIA3Automation();

            var serializerOptions = new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            };

            string? line;
            while ((line = Console.ReadLine()) is not null)
            {
                if (string.IsNullOrWhiteSpace(line))
                {
                    continue;
                }

                var response = HandleRequest(line, automation, options);
                Console.WriteLine(JsonSerializer.Serialize(response, serializerOptions));
                Console.Out.Flush();
                if (response.ExitRequested)
                {
                    break;
                }
            }

            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"native automation server failed: {ex}");
            return 1;
        }
    }

    private static NativeAutomationResponse HandleRequest(string rawLine, UIA3Automation automation, NativeAutomationServerOptions options)
    {
        string? requestId = null;
        try
        {
            using var document = JsonDocument.Parse(rawLine);
            var root = document.RootElement;
            requestId = root.TryGetProperty("id", out var idElement) ? idElement.GetString() : null;
            var command = root.TryGetProperty("command", out var commandElement)
                ? (commandElement.GetString() ?? string.Empty)
                : string.Empty;
            if (string.IsNullOrWhiteSpace(command))
            {
                throw new InvalidOperationException("Missing command.");
            }

            return command switch
            {
                "ping" => NativeAutomationResponse.Success(requestId, new Dictionary<string, object?>
                {
                    ["protocolVersion"] = 1,
                    ["repoRoot"] = options.RepoRoot,
                }),
                "shutdown" => NativeAutomationResponse.Success(requestId, new Dictionary<string, object?>(), exitRequested: true),
                "findTargetWindow" => NativeAutomationResponse.Success(requestId, HandleFindTargetWindow(root)),
                "getWindowInfo" => NativeAutomationResponse.Success(requestId, HandleGetWindowInfo(root)),
                "getForegroundWindow" => NativeAutomationResponse.Success(requestId, HandleGetForegroundWindow()),
                "focusWindow" => NativeAutomationResponse.Success(requestId, HandleFocusWindow(root)),
                "listRelatedWindows" => NativeAutomationResponse.Success(requestId, HandleListRelatedWindows(root)),
                "detectWindowedVisualShell" => NativeAutomationResponse.Success(requestId, HandleDetectWindowedVisualShell(root)),
                "detectRuntimeSignals" => NativeAutomationResponse.Success(requestId, HandleDetectRuntimeSignals(root, automation, options)),
                "getRuntimeLayoutState" => NativeAutomationResponse.Success(requestId, HandleGetRuntimeLayoutState(root, automation, options)),
                "selectRuntimeLayout" => NativeAutomationResponse.Success(requestId, HandleSelectRuntimeLayout(root, automation, options)),
                "invokeNamedControl" => NativeAutomationResponse.Success(requestId, HandleInvokeNamedControl(root, automation, options)),
                "pointerAction" => NativeAutomationResponse.Success(requestId, HandlePointerAction(root)),
                "sendKey" => NativeAutomationResponse.Success(requestId, HandleSendKey(root)),
                _ => NativeAutomationResponse.Failure(requestId, $"Unsupported command: {command}"),
            };
        }
        catch (Exception ex)
        {
            return NativeAutomationResponse.Failure(requestId, ex.Message);
        }
    }

    private static Dictionary<string, object?> HandleFindTargetWindow(JsonElement root)
    {
        var titleKeywords = ReadStringList(root, "titleKeywords");
        var processNames = ReadStringList(root, "processNames");
        var selection = NativeTargetSelector.SelectBestTarget(titleKeywords, processNames);
        return new Dictionary<string, object?>
        {
            ["window"] = selection.Window,
            ["candidates"] = selection.Candidates,
        };
    }

    private static Dictionary<string, object?> HandleGetWindowInfo(JsonElement root)
    {
        var hwnd = ReadHwnd(root, "hwnd");
        var window = NativeWindowDescriptor.FromHandle(hwnd);
        return new Dictionary<string, object?>
        {
            ["window"] = window,
        };
    }

    private static Dictionary<string, object?> HandleGetForegroundWindow()
    {
        var hwnd = NativeWin32.GetForegroundWindow();
        return new Dictionary<string, object?>
        {
            ["window"] = hwnd == IntPtr.Zero ? null : NativeWindowDescriptor.FromHandle(hwnd),
        };
    }

    private static Dictionary<string, object?> HandleFocusWindow(JsonElement root)
    {
        var hwnd = ReadHwnd(root, "hwnd");
        var focused = NativeWin32.TryActivateWindow(hwnd);
        return new Dictionary<string, object?>
        {
            ["focused"] = focused,
            ["foregroundHwnd"] = NativeWin32.GetForegroundWindow().ToInt64(),
        };
    }

    private static Dictionary<string, object?> HandleListRelatedWindows(JsonElement root)
    {
        var target = NativeWindowDescriptor.FromHandle(ReadHwnd(root, "hwnd"));
        var renderProcessNames = ReadStringList(root, "renderProcessNames");
        var windows = NativeTargetSelector.ListRelatedWindows(target, renderProcessNames);
        return new Dictionary<string, object?>
        {
            ["windows"] = windows,
        };
    }

    private static Dictionary<string, object?> HandleDetectWindowedVisualShell(JsonElement root)
    {
        var target = NativeWindowDescriptor.FromHandle(ReadHwnd(root, "hwnd"));
        var metrics = NativeWindowedVisualShellProbe.Analyze(target.ClientRect);
        return new Dictionary<string, object?>
        {
            ["windowedVisualShellLikely"] = metrics.WindowedShellLike,
            ["windowedVisualShellMetrics"] = metrics,
        };
    }

    private static Dictionary<string, object?> HandleDetectRuntimeSignals(
        JsonElement root,
        UIA3Automation automation,
        NativeAutomationServerOptions options)
    {
        var target = NativeWindowDescriptor.FromHandle(ReadHwnd(root, "hwnd"));
        var renderProcessNames = ReadStringList(root, "renderProcessNames");
        var treeDepth = ReadInt(root, "treeDepth", options.TreeDepth, minValue: 1, maxValue: 12);
        var openLayoutPanel = ReadBool(root, "openLayoutPanel", false);
        var result = NativeUiaBridge.DetectRuntimeSignals(
            automation,
            target,
            NativeTargetSelector.ListRelatedWindows(target, renderProcessNames),
            treeDepth,
            openLayoutPanel);
        return new Dictionary<string, object?>
        {
            ["windowedMarkers"] = result.WindowedMarkers,
            ["windowedVisualShellLikely"] = result.WindowedVisualShellLikely,
            ["windowedVisualShellMetrics"] = result.WindowedVisualShellMetrics,
            ["fullscreenToggleVisible"] = result.FullscreenToggleVisible,
            ["fullscreenToggleChecked"] = result.FullscreenToggleChecked,
            ["splitControlFound"] = result.SplitControlFound,
            ["layoutSections"] = result.LayoutSections,
            ["layoutOptions"] = result.LayoutOptions,
        };
    }

    private static Dictionary<string, object?> HandleGetRuntimeLayoutState(
        JsonElement root,
        UIA3Automation automation,
        NativeAutomationServerOptions options)
    {
        var target = NativeWindowDescriptor.FromHandle(ReadHwnd(root, "hwnd"));
        var renderProcessNames = ReadStringList(root, "renderProcessNames");
        var treeDepth = ReadInt(root, "treeDepth", options.TreeDepth, minValue: 1, maxValue: 12);
        var openLayoutPanel = ReadBool(root, "openLayoutPanel", true);
        var closePanel = ReadBool(root, "closePanel", false);
        var state = NativeUiaBridge.GetRuntimeLayoutState(
            automation,
            target,
            NativeTargetSelector.ListRelatedWindows(target, renderProcessNames),
            treeDepth,
            openLayoutPanel,
            closePanel);

        return new Dictionary<string, object?>
        {
            ["panelVisible"] = state.PanelVisible,
            ["panelOpened"] = state.PanelOpened,
            ["panelClosed"] = state.PanelClosed,
            ["splitControlFound"] = state.SplitControlFound,
            ["resolvedOptions"] = state.ResolvedOptions,
            ["selectedLayout"] = state.SelectedLayout,
            ["selectedSection"] = state.SelectedSection,
            ["selectedLabel"] = state.SelectedLabel,
            ["layoutSections"] = state.LayoutSections,
            ["layoutOptions"] = state.LayoutOptions,
        };
    }

    private static Dictionary<string, object?> HandleSelectRuntimeLayout(
        JsonElement root,
        UIA3Automation automation,
        NativeAutomationServerOptions options)
    {
        var target = NativeWindowDescriptor.FromHandle(ReadHwnd(root, "hwnd"));
        var renderProcessNames = ReadStringList(root, "renderProcessNames");
        var treeDepth = ReadInt(root, "treeDepth", options.TreeDepth, minValue: 1, maxValue: 12);
        var section = ReadString(root, "section");
        var label = ReadString(root, "label");
        var closePanel = ReadBool(root, "closePanel", false);
        var selection = NativeUiaBridge.SelectRuntimeLayoutOption(
            automation,
            target,
            NativeTargetSelector.ListRelatedWindows(target, renderProcessNames),
            treeDepth,
            section,
            label,
            closePanel);

        return new Dictionary<string, object?>
        {
            ["success"] = selection.Success,
            ["alreadySelected"] = selection.AlreadySelected,
            ["panelVisible"] = selection.PanelVisible,
            ["panelOpened"] = selection.PanelOpened,
            ["panelClosed"] = selection.PanelClosed,
            ["option"] = selection.Option,
            ["selectedLayout"] = selection.SelectedLayout,
            ["selectedSection"] = selection.SelectedSection,
            ["selectedLabel"] = selection.SelectedLabel,
            ["method"] = selection.Method,
            ["clickedPoint"] = selection.ClickedPoint,
        };
    }

    private static Dictionary<string, object?> HandleInvokeNamedControl(
        JsonElement root,
        UIA3Automation automation,
        NativeAutomationServerOptions options)
    {
        var target = NativeWindowDescriptor.FromHandle(ReadHwnd(root, "hwnd"));
        var controlName = ReadString(root, "controlName");
        var renderProcessNames = ReadStringList(root, "renderProcessNames");
        var treeDepth = ReadInt(root, "treeDepth", options.TreeDepth, minValue: 1, maxValue: 12);
        var control = NativeUiaBridge.FindFirstControlByName(
            automation,
            target,
            NativeTargetSelector.ListRelatedWindows(target, renderProcessNames),
            controlName,
            treeDepth);
        if (control is null)
        {
            throw new InvalidOperationException($"Control not found: {controlName}");
        }

        var attempt = NativeUiaBridge.TryInvoke(control);
        return new Dictionary<string, object?>
        {
            ["success"] = attempt.Success,
            ["method"] = attempt.Method,
            ["element"] = attempt.Element,
            ["notes"] = attempt.Notes,
        };
    }

    private static Dictionary<string, object?> HandlePointerAction(JsonElement root)
    {
        var x = ReadInt(root, "x", 0);
        var y = ReadInt(root, "y", 0);
        var isDouble = ReadBool(root, "double", false);
        var restoreCursor = ReadBool(root, "restoreCursor", true);
        var result = NativeInputBridge.PointerAction(x, y, isDouble, restoreCursor);
        return new Dictionary<string, object?>
        {
            ["performed"] = result,
        };
    }

    private static Dictionary<string, object?> HandleSendKey(JsonElement root)
    {
        var key = ReadString(root, "key").Trim().ToLowerInvariant();
        var performed = key switch
        {
            "escape" => NativeInputBridge.SendEscape(),
            "alt_f4" => NativeInputBridge.SendAltF4(),
            _ => throw new InvalidOperationException($"Unsupported sendKey value: {key}"),
        };
        return new Dictionary<string, object?>
        {
            ["performed"] = performed,
        };
    }

    private static string ReadString(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var property))
        {
            throw new InvalidOperationException($"Missing property: {propertyName}");
        }
        return property.GetString() ?? string.Empty;
    }

    private static List<string> ReadStringList(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.Array)
        {
            return [];
        }
        var values = new List<string>();
        foreach (var item in property.EnumerateArray())
        {
            var value = item.GetString();
            if (!string.IsNullOrWhiteSpace(value))
            {
                values.Add(value);
            }
        }
        return values;
    }

    private static IntPtr ReadHwnd(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var property))
        {
            throw new InvalidOperationException($"Missing property: {propertyName}");
        }
        return property.ValueKind switch
        {
            JsonValueKind.Number => new IntPtr(property.GetInt64()),
            JsonValueKind.String when long.TryParse(property.GetString(), out var parsed) => new IntPtr(parsed),
            _ => throw new InvalidOperationException($"Invalid hwnd value for {propertyName}"),
        };
    }

    private static bool ReadBool(JsonElement root, string propertyName, bool defaultValue)
    {
        if (!root.TryGetProperty(propertyName, out var property))
        {
            return defaultValue;
        }
        return property.ValueKind == JsonValueKind.True
            || (property.ValueKind == JsonValueKind.String && bool.TryParse(property.GetString(), out var parsed) && parsed);
    }

    private static int ReadInt(JsonElement root, string propertyName, int defaultValue, int minValue = int.MinValue, int maxValue = int.MaxValue)
    {
        if (!root.TryGetProperty(propertyName, out var property))
        {
            return defaultValue;
        }

        var value = property.ValueKind switch
        {
            JsonValueKind.Number => property.GetInt32(),
            JsonValueKind.String when int.TryParse(property.GetString(), out var parsed) => parsed,
            _ => defaultValue,
        };
        return Math.Clamp(value, minValue, maxValue);
    }
}

internal sealed class NativeAutomationServerOptions
{
    public string RepoRoot { get; private set; } = Directory.GetCurrentDirectory();
    public int TreeDepth { get; private set; } = 4;

    public static NativeAutomationServerOptions Parse(string[] args)
    {
        var options = new NativeAutomationServerOptions();
        for (var index = 0; index < args.Length; index++)
        {
            switch (args[index])
            {
                case "--repo-root":
                    options.RepoRoot = RequireValue(args, ref index, "--repo-root");
                    break;
                case "--tree-depth":
                    if (!int.TryParse(RequireValue(args, ref index, "--tree-depth"), out var treeDepth))
                    {
                        throw new InvalidOperationException("--tree-depth must be an integer.");
                    }
                    options.TreeDepth = Math.Clamp(treeDepth, 1, 12);
                    break;
                default:
                    throw new InvalidOperationException($"Unsupported server option: {args[index]}");
            }
        }

        return options;
    }

    private static string RequireValue(string[] args, ref int index, string optionName)
    {
        if (index + 1 >= args.Length)
        {
            throw new InvalidOperationException($"Missing value for {optionName}");
        }
        index += 1;
        return args[index];
    }
}

internal sealed class NativeAutomationResponse
{
    public string? Id { get; set; }
    public bool Ok { get; set; }
    public object? Result { get; set; }
    public string? Error { get; set; }
    [JsonIgnore]
    public bool ExitRequested { get; set; }

    public static NativeAutomationResponse Success(string? id, object? result, bool exitRequested = false)
    {
        return new NativeAutomationResponse
        {
            Id = id,
            Ok = true,
            Result = result,
            ExitRequested = exitRequested,
        };
    }

    public static NativeAutomationResponse Failure(string? id, string error)
    {
        return new NativeAutomationResponse
        {
            Id = id,
            Ok = false,
            Error = error,
        };
    }
}

internal static class NativeTargetSelector
{
    public static NativeTargetSelection SelectBestTarget(IReadOnlyList<string> titleKeywords, IReadOnlyList<string> processNames)
    {
        var windows = Win32WindowInspector.EnumerateVisibleWindows();
        var candidates = new List<NativeCandidateDescriptor>();
        foreach (var window in windows)
        {
            var processName = NormalizeProcessName(window.ProcessName);
            var titleMatch = titleKeywords.Any(keyword =>
                !string.IsNullOrWhiteSpace(keyword)
                && window.Title.Contains(keyword, StringComparison.OrdinalIgnoreCase));
            var processMatch = processNames.Any(name => NormalizeProcessName(name) == processName);
            if (!titleMatch && !processMatch)
            {
                continue;
            }

            candidates.Add(NativeCandidateDescriptor.From(window, titleMatch, processMatch));
        }

        if (candidates.Count == 0)
        {
            throw new InvalidOperationException("No matching target window was found.");
        }

        var processMatched = candidates.Where(item => item.ProcessMatch).ToList();
        var exactMatched = processMatched.Where(item => item.TitleMatch).ToList();
        var working = exactMatched.Count > 0 ? exactMatched : (processMatched.Count > 0 ? processMatched : candidates);
        working = working.Where(item => !string.IsNullOrWhiteSpace(item.Title)).DefaultIfEmpty(working[0]).ToList();
        working = working
            .OrderByDescending(item => item.ProcessMatch && item.TitleMatch)
            .ThenByDescending(item => item.TitleMatch)
            .ThenByDescending(item => !item.IsIconic)
            .ThenByDescending(item => item.IsForeground)
            .ThenByDescending(item => item.Area)
            .ToList();

        var best = working[0];
        return new NativeTargetSelection
        {
            Window = NativeWindowDescriptor.FromHandle(new IntPtr(best.Hwnd)),
            Candidates = working,
        };
    }

    public static List<NativeWindowDescriptor> ListRelatedWindows(NativeWindowDescriptor target, IReadOnlyList<string> renderProcessNames)
    {
        var results = new List<NativeWindowDescriptor>();
        foreach (var window in Win32WindowInspector.EnumerateVisibleWindows())
        {
            if (window.Hwnd.ToInt64() == target.Hwnd)
            {
                continue;
            }
            if (!window.IsVisible)
            {
                continue;
            }

            NativeWindowDescriptor descriptor;
            try
            {
                descriptor = NativeWindowDescriptor.From(window);
            }
            catch
            {
                continue;
            }
            if (descriptor.ProcessId == target.ProcessId)
            {
                results.Add(descriptor);
                continue;
            }
            if (descriptor.OwnerHwnd == target.Hwnd)
            {
                results.Add(descriptor);
                continue;
            }
            if (renderProcessNames.Count > 0 && renderProcessNames.Any(name => NormalizeProcessName(name) == NormalizeProcessName(descriptor.ProcessName)))
            {
                if (descriptor.WindowRect.IntersectionRatio(target.WindowRect) >= 0.80)
                {
                    results.Add(descriptor);
                }
            }
        }
        return results
            .OrderByDescending(item => item.OwnerHwnd == target.Hwnd)
            .ThenByDescending(item => item.WindowRect.Area)
            .ToList();
    }

    private static string NormalizeProcessName(string? processName)
    {
        var normalized = (processName ?? string.Empty).Trim();
        if (normalized.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
        {
            return normalized.ToLowerInvariant();
        }
        return $"{normalized}.exe".ToLowerInvariant();
    }
}

internal sealed class NativeTargetSelection
{
    public NativeWindowDescriptor Window { get; set; } = new();
    public List<NativeCandidateDescriptor> Candidates { get; set; } = [];
}

internal sealed class NativeCandidateDescriptor
{
    public long Hwnd { get; set; }
    public string HwndHex => $"0x{Hwnd:X}";
    public string Title { get; set; } = string.Empty;
    public string ProcessName { get; set; } = string.Empty;
    public bool TitleMatch { get; set; }
    public bool ProcessMatch { get; set; }
    public bool IsForeground { get; set; }
    public bool IsIconic { get; set; }
    public int Area { get; set; }

    public static NativeCandidateDescriptor From(Win32WindowInfo window, bool titleMatch, bool processMatch)
    {
        return new NativeCandidateDescriptor
        {
            Hwnd = window.Hwnd.ToInt64(),
            Title = window.Title,
            ProcessName = window.ProcessName,
            TitleMatch = titleMatch,
            ProcessMatch = processMatch,
            IsForeground = window.IsForeground,
            IsIconic = NativeWin32.IsIconic(window.Hwnd),
            Area = window.Area,
        };
    }
}

internal sealed class NativeWindowDescriptor
{
    public long Hwnd { get; set; }
    public string HwndHex => $"0x{Hwnd:X}";
    public int ProcessId { get; set; }
    public string ProcessName { get; set; } = string.Empty;
    public string Title { get; set; } = string.Empty;
    public long OwnerHwnd { get; set; }
    public string OwnerHwndHex => $"0x{OwnerHwnd:X}";
    public bool IsVisible { get; set; }
    public bool IsForeground { get; set; }
    public bool IsIconic { get; set; }
    public RectDto WindowRect { get; set; } = new();
    public RectDto ClientRect { get; set; } = new();
    public RectDto MonitorRect { get; set; } = new();

    public static NativeWindowDescriptor From(Win32WindowInfo window)
    {
        return FromHandle(window.Hwnd);
    }

    public static NativeWindowDescriptor FromHandle(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero)
        {
            throw new InvalidOperationException("Invalid hwnd=0.");
        }

        var processId = NativeWin32.GetWindowProcessId(hwnd);
        var processName = NativeWin32.TryGetProcessName(processId);
        var owner = NativeWin32.GetOwnerWindow(hwnd);
        var clientRect = NativeWin32.GetClientRectOnScreen(hwnd);
        if (clientRect.Width <= 0 || clientRect.Height <= 0)
        {
            throw new InvalidOperationException($"Invalid client rect for hwnd={hwnd.ToInt64()}");
        }

        return new NativeWindowDescriptor
        {
            Hwnd = hwnd.ToInt64(),
            ProcessId = processId,
            ProcessName = processName,
            Title = NativeWin32.GetWindowTextManaged(hwnd),
            OwnerHwnd = owner.ToInt64(),
            IsVisible = NativeWin32.IsWindowVisible(hwnd),
            IsForeground = hwnd == NativeWin32.GetForegroundWindow(),
            IsIconic = NativeWin32.IsIconic(hwnd),
            WindowRect = NativeWin32.GetWindowRectDto(hwnd),
            ClientRect = clientRect,
            MonitorRect = NativeWin32.GetMonitorRect(hwnd),
        };
    }
}

internal static class NativeUiaBridge
{
    private static readonly string[] WindowedMarkers =
    [
        "收藏夹",
        "打开文件夹",
        "搜索",
        "全部收藏",
        "视频监控配置",
    ];

    private static readonly string[] LayoutSectionNames =
    [
        "平均",
        "高亮分割",
        "水平",
        "垂直",
        "其他",
    ];

    private static readonly string[] LayoutOptionNames =
    [
        "4",
        "6",
        "9",
        "12",
        "13",
    ];

    private static readonly string[] ToggleNames =
    [
        "全屏",
        "退出全屏",
        "窗口分割",
    ];

    public static NativeRuntimeSignalsResult DetectRuntimeSignals(
        UIA3Automation automation,
        NativeWindowDescriptor target,
        IReadOnlyList<NativeWindowDescriptor> relatedWindows,
        int treeDepth,
        bool openLayoutPanel)
    {
        var allRoots = BuildRoots(automation, target, relatedWindows);
        var result = ScanRuntimeSignals(allRoots, treeDepth);
        result.WindowedVisualShellMetrics = NativeWindowedVisualShellProbe.Analyze(target.ClientRect);
        if (openLayoutPanel && !PanelLooksVisible(result))
        {
            var splitControl = FindFirstControlByName(automation, target, relatedWindows, "窗口分割", treeDepth);
            if (splitControl is not null)
            {
                TryInvoke(splitControl);
                Thread.Sleep(400);
                allRoots = BuildRoots(automation, target, relatedWindows);
                result = ScanRuntimeSignals(allRoots, treeDepth);
            }
        }

        return result;
    }

    public static NativeRuntimeLayoutStateResult GetRuntimeLayoutState(
        UIA3Automation automation,
        NativeWindowDescriptor target,
        IReadOnlyList<NativeWindowDescriptor> relatedWindows,
        int treeDepth,
        bool openLayoutPanel,
        bool closePanel)
    {
        var roots = BuildRoots(automation, target, relatedWindows);
        var signals = ScanRuntimeSignals(roots, treeDepth);
        var panelVisible = PanelLooksVisible(signals);
        var panelOpened = false;
        var panelClosed = false;

        if (openLayoutPanel && !panelVisible)
        {
            var splitControl = FindFirstControlByName(automation, target, relatedWindows, "窗口分割", treeDepth);
            if (splitControl is not null)
            {
                TryInvoke(splitControl);
                Thread.Sleep(400);
                roots = BuildRoots(automation, target, relatedWindows);
                signals = ScanRuntimeSignals(roots, treeDepth);
                panelVisible = PanelLooksVisible(signals);
                panelOpened = panelVisible;
            }
        }

        var resolvedOptions = BuildRuntimeLayoutOptions(signals.LayoutSections, signals.LayoutOptions);
        var selectedOption = resolvedOptions.FirstOrDefault(option => option.Selected);

        if (closePanel && panelVisible)
        {
            var closeResult = AttemptCloseLayoutPanel(
                automation,
                target,
                relatedWindows,
                treeDepth,
                resolvedOptions,
                signals);
            panelClosed = closeResult.Confirmed;
            signals = closeResult.SignalsAfterClose;
        }

        return new NativeRuntimeLayoutStateResult
        {
            PanelVisible = panelVisible,
            PanelOpened = panelOpened,
            PanelClosed = panelClosed,
            SplitControlFound = signals.SplitControlFound,
            LayoutSections = signals.LayoutSections,
            LayoutOptions = signals.LayoutOptions,
            ResolvedOptions = resolvedOptions,
            SelectedLayout = TryParseLayout(selectedOption?.Label),
            SelectedSection = selectedOption?.Section,
            SelectedLabel = selectedOption?.Label,
            CloseMethod = closePanel ? (panelClosed ? "confirmed" : "failed") : string.Empty,
        };
    }

    public static NativeRuntimeLayoutSelectionResult SelectRuntimeLayoutOption(
        UIA3Automation automation,
        NativeWindowDescriptor target,
        IReadOnlyList<NativeWindowDescriptor> relatedWindows,
        int treeDepth,
        string section,
        string label,
        bool closePanel)
    {
        var roots = BuildRoots(automation, target, relatedWindows);
        var signals = ScanRuntimeSignals(roots, treeDepth);
        var panelVisible = PanelLooksVisible(signals);
        var panelOpened = false;
        if (!panelVisible)
        {
            var splitControl = FindFirstControlByName(automation, target, relatedWindows, "窗口分割", treeDepth);
            if (splitControl is null)
            {
                throw new InvalidOperationException("Could not find split-layout control before selecting runtime layout.");
            }
            TryInvoke(splitControl);
            Thread.Sleep(400);
            roots = BuildRoots(automation, target, relatedWindows);
            signals = ScanRuntimeSignals(roots, treeDepth);
            panelVisible = PanelLooksVisible(signals);
            panelOpened = panelVisible;
        }
        if (!panelVisible)
        {
            throw new InvalidOperationException("Layout panel is not visible after native open attempt.");
        }

        var matches = ScanInterestingControlMatches(roots, treeDepth);
        var resolvedOptions = BuildRuntimeLayoutOptions(matches
            .Where(match => LayoutSectionNames.Any(sectionName => NameEquals(match.Control.Name, sectionName)))
            .Select(match => match.Control)
            .ToList(), matches
            .Where(match => LayoutOptionNames.Any(optionName => NameEquals(match.Control.Name, optionName)))
            .Select(match => match.Control)
            .ToList());

        var targetOption = resolvedOptions.FirstOrDefault(option =>
            NameEquals(option.Section, section) && NameEquals(option.Label, label));
        if (targetOption is null)
        {
            throw new InvalidOperationException($"Could not resolve runtime layout option: {section}/{label}");
        }

        var method = "noop";
        if (!targetOption.Selected)
        {
            var clickX = targetOption.Bounds.Left + Math.Max(1, targetOption.Bounds.Width / 2);
            var clickY = targetOption.Bounds.Top + Math.Max(1, targetOption.Bounds.Height / 2);
            NativeInputBridge.PointerAction(clickX, clickY, false, true);
            method = "pointerAction";
            Thread.Sleep(450);
            roots = BuildRoots(automation, target, relatedWindows);
            matches = ScanInterestingControlMatches(roots, treeDepth);
            resolvedOptions = BuildRuntimeLayoutOptions(matches
                .Where(match => LayoutSectionNames.Any(sectionName => NameEquals(match.Control.Name, sectionName)))
                .Select(match => match.Control)
                .ToList(), matches
                .Where(match => LayoutOptionNames.Any(optionName => NameEquals(match.Control.Name, optionName)))
                .Select(match => match.Control)
                .ToList());
            targetOption = resolvedOptions.FirstOrDefault(option =>
                NameEquals(option.Section, section) && NameEquals(option.Label, label)) ?? targetOption;
        }

        var selectedOption = resolvedOptions.FirstOrDefault(option => option.Selected);
        var panelClosed = false;
        var closeMethod = string.Empty;
        var closeFallbackUsed = false;
        if (closePanel)
        {
            var closeResult = AttemptCloseLayoutPanel(
                automation,
                target,
                relatedWindows,
                treeDepth,
                resolvedOptions,
                ScanRuntimeSignals(roots, treeDepth));
            panelClosed = closeResult.Confirmed;
            closeMethod = closeResult.Method;
            closeFallbackUsed = closeResult.FallbackUsed;
        }

        return new NativeRuntimeLayoutSelectionResult
        {
            Success = targetOption.Selected,
            AlreadySelected = targetOption.Selected && method == "noop",
            SelectionConfirmed = targetOption.Selected,
            PanelVisible = panelVisible,
            PanelOpened = panelOpened,
            PanelClosed = panelClosed,
            Option = targetOption,
            SelectedLayout = TryParseLayout(selectedOption?.Label),
            SelectedSection = selectedOption?.Section,
            SelectedLabel = selectedOption?.Label,
            Method = method,
            CloseMethod = closeMethod,
            CloseFallbackUsed = closeFallbackUsed,
            ClickedPoint = method == "pointerAction"
                ? new Dictionary<string, int>
                {
                    ["x"] = targetOption.Bounds.Left + Math.Max(1, targetOption.Bounds.Width / 2),
                    ["y"] = targetOption.Bounds.Top + Math.Max(1, targetOption.Bounds.Height / 2),
                }
                : null,
        };
    }

    public static AutomationElement? FindFirstControlByName(
        UIA3Automation automation,
        NativeWindowDescriptor target,
        IReadOnlyList<NativeWindowDescriptor> relatedWindows,
        string controlName,
        int maxDepth)
    {
        var roots = new List<IntPtr> { new(target.Hwnd) };
        roots.AddRange(relatedWindows.Select(window => new IntPtr(window.Hwnd)));
        foreach (var hwnd in roots)
        {
            var root = TryFromHandle(automation, hwnd);
            if (root is null)
            {
                continue;
            }
            var queue = new Queue<(AutomationElement Element, int Depth)>();
            queue.Enqueue((root, 0));
            while (queue.Count > 0)
            {
                var (current, depth) = queue.Dequeue();
                if (NameEquals(current.Name, controlName))
                {
                    return current;
                }
                if (depth >= maxDepth)
                {
                    continue;
                }
                AutomationElement[] children;
                try
                {
                    children = current.FindAllChildren();
                }
                catch
                {
                    continue;
                }
                foreach (var child in children)
                {
                    queue.Enqueue((child, depth + 1));
                }
            }
        }
        return null;
    }

    public static InvokeAttempt TryInvoke(AutomationElement element)
    {
        var attempt = new InvokeAttempt
        {
            Element = ElementSnapshot.From(element, IntPtr.Zero, "invoke_target"),
        };

        try
        {
            element.Focus();
        }
        catch (Exception ex)
        {
            attempt.Notes.Add($"focus failed: {ex.Message}");
        }

        try
        {
            var invoke = element.Patterns.Invoke.PatternOrDefault;
            if (invoke is not null)
            {
                invoke.Invoke();
                attempt.Success = true;
                attempt.Method = "InvokePattern";
                return attempt;
            }
        }
        catch (Exception ex)
        {
            attempt.Notes.Add($"invoke pattern failed: {ex.Message}");
        }

        try
        {
            var legacy = element.Patterns.LegacyIAccessible.PatternOrDefault;
            if (legacy is not null)
            {
                legacy.DoDefaultAction();
                attempt.Success = true;
                attempt.Method = "LegacyIAccessible.DoDefaultAction";
                return attempt;
            }
        }
        catch (Exception ex)
        {
            attempt.Notes.Add($"legacy action failed: {ex.Message}");
        }

        attempt.Success = false;
        attempt.Method = "none";
        return attempt;
    }

    private static AutomationElement? TryFromHandle(UIA3Automation automation, IntPtr hwnd)
    {
        try
        {
            return automation.FromHandle(hwnd);
        }
        catch
        {
            return null;
        }
    }

    private static List<(AutomationElement Root, string Source)> BuildRoots(
        UIA3Automation automation,
        NativeWindowDescriptor target,
        IReadOnlyList<NativeWindowDescriptor> relatedWindows)
    {
        var allRoots = new List<(AutomationElement Root, string Source)>();
        var mainRoot = TryFromHandle(automation, new IntPtr(target.Hwnd));
        if (mainRoot is not null)
        {
            allRoots.Add((mainRoot, "main"));
        }
        foreach (var window in relatedWindows)
        {
            var relatedRoot = TryFromHandle(automation, new IntPtr(window.Hwnd));
            if (relatedRoot is not null)
            {
                allRoots.Add((relatedRoot, "related"));
            }
        }
        return allRoots;
    }

    private static NativeRuntimeSignalsResult ScanRuntimeSignals(
        IReadOnlyList<(AutomationElement Root, string Source)> allRoots,
        int treeDepth)
    {
        var result = new NativeRuntimeSignalsResult();
        foreach (var (root, source) in allRoots)
        {
            foreach (var match in ScanInterestingControls(root, source, treeDepth))
            {
                if (WindowedMarkers.Any(marker => NameEquals(match.Name, marker)) && !result.WindowedMarkers.Contains(match.Name))
                {
                    result.WindowedMarkers.Add(match.Name);
                }
                if (NameEquals(match.Name, "窗口分割"))
                {
                    result.SplitControlFound = true;
                }
                if (ToggleNames.Any(toggle => NameEquals(match.Name, toggle)))
                {
                    result.FullscreenToggleVisible = result.FullscreenToggleVisible || NameEquals(match.Name, "全屏") || NameEquals(match.Name, "退出全屏");
                }
                if (LayoutSectionNames.Any(section => NameEquals(match.Name, section)))
                {
                    result.LayoutSections.Add(match);
                }
                if (LayoutOptionNames.Any(option => NameEquals(match.Name, option)))
                {
                    result.LayoutOptions.Add(match);
                }
                if ((NameEquals(match.Name, "全屏") || NameEquals(match.Name, "退出全屏")) && match.Selected)
                {
                    result.FullscreenToggleChecked = true;
                }
            }
        }
        return result;
    }

    private static bool PanelLooksVisible(NativeRuntimeSignalsResult result)
    {
        return result.LayoutSections.Count > 0 || result.LayoutOptions.Count > 0;
    }

    private static NativeRuntimeLayoutCloseAttemptResult AttemptCloseLayoutPanel(
        UIA3Automation automation,
        NativeWindowDescriptor target,
        IReadOnlyList<NativeWindowDescriptor> relatedWindows,
        int treeDepth,
        IReadOnlyList<NativeRuntimeLayoutOptionDescriptor> resolvedOptions,
        NativeRuntimeSignalsResult currentSignals)
    {
        var result = new NativeRuntimeLayoutCloseAttemptResult
        {
            SignalsAfterClose = currentSignals,
        };
        if (!PanelLooksVisible(currentSignals))
        {
            result.Confirmed = true;
            result.Method = "already_closed";
            return result;
        }

        var splitControl = FindFirstControlByName(automation, target, relatedWindows, "窗口分割", treeDepth);
        if (splitControl is not null)
        {
            TryInvoke(splitControl);
            Thread.Sleep(250);
            var signalsAfterToggle = ScanRuntimeSignals(BuildRoots(automation, target, relatedWindows), treeDepth);
            if (!PanelLooksVisible(signalsAfterToggle))
            {
                result.Confirmed = true;
                result.Method = "split_invoke";
                result.SignalsAfterClose = signalsAfterToggle;
                return result;
            }
            result.SignalsAfterClose = signalsAfterToggle;
        }

        NativeInputBridge.SendEscape();
        Thread.Sleep(220);
        var signalsAfterEscape = ScanRuntimeSignals(BuildRoots(automation, target, relatedWindows), treeDepth);
        if (!PanelLooksVisible(signalsAfterEscape))
        {
            result.Confirmed = true;
            result.Method = "escape";
            result.FallbackUsed = true;
            result.SignalsAfterClose = signalsAfterEscape;
            return result;
        }
        result.SignalsAfterClose = signalsAfterEscape;

        var panelBounds = BuildPanelBounds(currentSignals.LayoutSections, resolvedOptions);
        if (panelBounds is not null)
        {
            var dismissPoint = ResolveDismissPoint(target.ClientRect, panelBounds);
            NativeInputBridge.PointerAction(dismissPoint.X, dismissPoint.Y, false, true);
            Thread.Sleep(250);
            var signalsAfterDismiss = ScanRuntimeSignals(BuildRoots(automation, target, relatedWindows), treeDepth);
            if (!PanelLooksVisible(signalsAfterDismiss))
            {
                result.Confirmed = true;
                result.Method = "dismiss_click";
                result.FallbackUsed = true;
                result.SignalsAfterClose = signalsAfterDismiss;
                return result;
            }
            result.SignalsAfterClose = signalsAfterDismiss;
        }

        result.Confirmed = false;
        result.Method = "failed";
        result.FallbackUsed = true;
        return result;
    }

    private static RectDto? BuildPanelBounds(
        IReadOnlyList<NativeInterestingControl> layoutSections,
        IReadOnlyList<NativeRuntimeLayoutOptionDescriptor> resolvedOptions)
    {
        var rects = new List<RectDto>();
        rects.AddRange(layoutSections.Select(item => item.Bounds).Where(bounds => bounds.Width > 0 && bounds.Height > 0));
        rects.AddRange(resolvedOptions.Select(item => item.Bounds).Where(bounds => bounds.Width > 0 && bounds.Height > 0));
        if (rects.Count == 0)
        {
            return null;
        }
        return new RectDto(
            rects.Min(item => item.Left),
            rects.Min(item => item.Top),
            rects.Max(item => item.Right),
            rects.Max(item => item.Bottom)
        );
    }

    private static NativeWin32.POINT ResolveDismissPoint(RectDto clientRect, RectDto panelBounds)
    {
        var x = Math.Max(clientRect.Left + 20, panelBounds.Left - 80);
        if (x >= panelBounds.Left)
        {
            x = Math.Max(clientRect.Left + 8, panelBounds.Left - 20);
        }
        var y = Math.Min(
            Math.Max(clientRect.Top + 24, panelBounds.Top + 24),
            Math.Max(clientRect.Top + 24, clientRect.Bottom - 24));
        return new NativeWin32.POINT { X = x, Y = y };
    }

    private static List<NativeRuntimeLayoutOptionDescriptor> BuildRuntimeLayoutOptions(
        IReadOnlyList<NativeInterestingControl> layoutSections,
        IReadOnlyList<NativeInterestingControl> layoutOptions)
    {
        var headerRows = layoutSections
            .Select(section => new KeyValuePair<string, int>(section.Name, section.Bounds.Top))
            .OrderBy(item => item.Value)
            .ToList();
        var resolved = new List<NativeRuntimeLayoutOptionDescriptor>();
        foreach (var option in layoutOptions.OrderBy(item => item.Bounds.Top).ThenBy(item => item.Bounds.Left))
        {
            var section = AssignLayoutSection(headerRows, option.Bounds.Top);
            if (string.IsNullOrWhiteSpace(section))
            {
                continue;
            }
            resolved.Add(new NativeRuntimeLayoutOptionDescriptor
            {
                Section = section,
                Label = option.Name,
                Bounds = option.Bounds,
                Selected = option.Selected,
                Source = option.Source,
                ControlType = option.ControlType,
            });
        }
        return resolved;
    }

    private static string? AssignLayoutSection(IReadOnlyList<KeyValuePair<string, int>> headerRows, int checkboxTop)
    {
        string? selected = null;
        foreach (var row in headerRows)
        {
            if (row.Value <= checkboxTop)
            {
                selected = row.Key;
                continue;
            }
            break;
        }
        return selected;
    }

    private static int? TryParseLayout(string? label)
    {
        return int.TryParse(label, out var parsed) ? parsed : null;
    }

    private static List<NativeInterestingControl> ScanInterestingControls(AutomationElement root, string source, int maxDepth)
    {
        return ScanInterestingControlMatches(root, source, maxDepth)
            .Select(match => match.Control)
            .ToList();
    }

    private static List<NativeInterestingControlMatch> ScanInterestingControlMatches(
        IReadOnlyList<(AutomationElement Root, string Source)> roots,
        int maxDepth)
    {
        var results = new List<NativeInterestingControlMatch>();
        foreach (var (root, source) in roots)
        {
            results.AddRange(ScanInterestingControlMatches(root, source, maxDepth));
        }
        return results;
    }

    private static List<NativeInterestingControlMatch> ScanInterestingControlMatches(AutomationElement root, string source, int maxDepth)
    {
        var results = new List<NativeInterestingControlMatch>();
        var queue = new Queue<(AutomationElement Element, int Depth)>();
        queue.Enqueue((root, 0));
        while (queue.Count > 0)
        {
            var (current, depth) = queue.Dequeue();
            if (IsInterestingControl(current))
            {
                results.Add(new NativeInterestingControlMatch
                {
                    Element = current,
                    Control = NativeInterestingControl.From(current, source),
                });
            }
            if (depth >= maxDepth)
            {
                continue;
            }
            AutomationElement[] children;
            try
            {
                children = current.FindAllChildren();
            }
            catch
            {
                continue;
            }
            foreach (var child in children)
            {
                queue.Enqueue((child, depth + 1));
            }
        }
        return results;
    }

    private static bool IsInterestingControl(AutomationElement element)
    {
        var name = (element.Name ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(name))
        {
            return false;
        }

        return WindowedMarkers.Any(marker => NameEquals(name, marker))
            || LayoutSectionNames.Any(marker => NameEquals(name, marker))
            || LayoutOptionNames.Any(marker => NameEquals(name, marker))
            || ToggleNames.Any(marker => NameEquals(name, marker));
    }

    private static bool NameEquals(string? actual, string expected)
    {
        return string.Equals((actual ?? string.Empty).Trim(), expected, StringComparison.OrdinalIgnoreCase);
    }
}

internal static class NativeWindowedVisualShellProbe
{
    private const int SampleColumns = 8;
    private const int SampleRows = 8;

    public static NativeWindowedVisualShellMetrics Analyze(RectDto clientRect)
    {
        var metrics = new NativeWindowedVisualShellMetrics();
        if (clientRect.Width < 240 || clientRect.Height < 180)
        {
            return metrics;
        }

        using var sampler = NativeScreenPixelSampler.TryCreate();
        if (sampler is null)
        {
            return metrics;
        }

        var left = SampleRegion(sampler, clientRect, 0.00, 0.00, 0.22, 1.00);
        var top = SampleRegion(sampler, clientRect, 0.00, 0.00, 1.00, 0.10);
        var preview = SampleRegion(sampler, clientRect, 0.24, 0.08, 1.00, 1.00);
        if (left.SampleCount == 0 || top.SampleCount == 0 || preview.SampleCount == 0)
        {
            return metrics;
        }

        metrics.ProbeSucceeded = true;
        metrics.WindowedShellLeftMean = left.Mean;
        metrics.WindowedShellLeftStd = left.Std;
        metrics.WindowedShellLeftBrightRatio = left.BrightRatio;
        metrics.WindowedShellLeftDarkRatio = left.DarkRatio;
        metrics.WindowedShellTopMean = top.Mean;
        metrics.WindowedShellTopStd = top.Std;
        metrics.WindowedShellTopBrightRatio = top.BrightRatio;
        metrics.WindowedShellTopDarkRatio = top.DarkRatio;
        metrics.WindowedShellPreviewMean = preview.Mean;
        metrics.WindowedShellPreviewStd = preview.Std;
        metrics.WindowedShellPreviewBrightRatio = preview.BrightRatio;
        metrics.WindowedShellPreviewDarkRatio = preview.DarkRatio;
        metrics.WindowedShellScore = Math.Round(
            (metrics.WindowedShellLeftBrightRatio * 55.0)
            + (metrics.WindowedShellTopBrightRatio * 35.0)
            + (Math.Max(0.0, metrics.WindowedShellLeftMean - metrics.WindowedShellPreviewMean) * 0.12),
            4);
        metrics.WindowedShellLike = LooksLike(metrics);
        return metrics;
    }

    private static NativeLumaRegionMetrics SampleRegion(
        NativeScreenPixelSampler sampler,
        RectDto clientRect,
        double leftRatio,
        double topRatio,
        double rightRatio,
        double bottomRatio)
    {
        var regionLeft = clientRect.Left + (int)Math.Round(clientRect.Width * leftRatio);
        var regionTop = clientRect.Top + (int)Math.Round(clientRect.Height * topRatio);
        var regionRight = clientRect.Left + (int)Math.Round(clientRect.Width * rightRatio);
        var regionBottom = clientRect.Top + (int)Math.Round(clientRect.Height * bottomRatio);
        regionRight = Math.Max(regionLeft + 1, regionRight);
        regionBottom = Math.Max(regionTop + 1, regionBottom);

        var regionWidth = Math.Max(1, regionRight - regionLeft);
        var regionHeight = Math.Max(1, regionBottom - regionTop);
        var columns = Math.Min(SampleColumns, Math.Max(4, regionWidth / 18));
        var rows = Math.Min(SampleRows, Math.Max(4, regionHeight / 18));
        var sum = 0.0;
        var sumSquares = 0.0;
        var bright = 0;
        var dark = 0;
        var count = 0;

        for (var row = 0; row < rows; row++)
        {
            var y = regionTop + (int)Math.Round(((row + 0.5) * regionHeight) / rows);
            y = Math.Clamp(y, regionTop, regionBottom - 1);
            for (var column = 0; column < columns; column++)
            {
                var x = regionLeft + (int)Math.Round(((column + 0.5) * regionWidth) / columns);
                x = Math.Clamp(x, regionLeft, regionRight - 1);
                if (!sampler.TryGetLuma(x, y, out var luma))
                {
                    continue;
                }

                sum += luma;
                sumSquares += luma * luma;
                if (luma >= 180.0)
                {
                    bright += 1;
                }
                if (luma < 60.0)
                {
                    dark += 1;
                }
                count += 1;
            }
        }

        if (count == 0)
        {
            return new NativeLumaRegionMetrics();
        }

        var mean = sum / count;
        var variance = Math.Max(0.0, (sumSquares / count) - (mean * mean));
        return new NativeLumaRegionMetrics
        {
            SampleCount = count,
            Mean = Math.Round(mean, 4),
            Std = Math.Round(Math.Sqrt(variance), 4),
            BrightRatio = Math.Round(bright / (double)count, 4),
            DarkRatio = Math.Round(dark / (double)count, 4),
        };
    }

    private static bool LooksLike(NativeWindowedVisualShellMetrics metrics)
    {
        return metrics.WindowedShellLeftMean >= 150.0
            && metrics.WindowedShellLeftBrightRatio >= 0.40
            && metrics.WindowedShellLeftDarkRatio <= 0.25
            && metrics.WindowedShellTopMean >= 95.0
            && metrics.WindowedShellTopBrightRatio >= 0.10
            && metrics.WindowedShellTopDarkRatio <= 0.40
            && (metrics.WindowedShellLeftMean - metrics.WindowedShellPreviewMean) >= 65.0
            && metrics.WindowedShellPreviewDarkRatio >= 0.45;
    }
}

internal sealed class NativeScreenPixelSampler : IDisposable
{
    private readonly IntPtr _screenDc;

    private NativeScreenPixelSampler(IntPtr screenDc)
    {
        _screenDc = screenDc;
    }

    public static NativeScreenPixelSampler? TryCreate()
    {
        var screenDc = NativeWin32.GetScreenDc();
        return screenDc == IntPtr.Zero ? null : new NativeScreenPixelSampler(screenDc);
    }

    public bool TryGetLuma(int x, int y, out double luma)
    {
        var pixel = NativeWin32.GetScreenPixel(_screenDc, x, y);
        if (pixel == NativeWin32.InvalidColorRef)
        {
            luma = 0.0;
            return false;
        }

        var red = (int)(pixel & 0xFF);
        var green = (int)((pixel >> 8) & 0xFF);
        var blue = (int)((pixel >> 16) & 0xFF);
        luma = (red * 0.299) + (green * 0.587) + (blue * 0.114);
        return true;
    }

    public void Dispose()
    {
        NativeWin32.ReleaseScreenDc(_screenDc);
    }
}

internal sealed class NativeRuntimeSignalsResult
{
    public List<string> WindowedMarkers { get; set; } = [];
    public NativeWindowedVisualShellMetrics WindowedVisualShellMetrics { get; set; } = new();
    public bool WindowedVisualShellLikely => WindowedVisualShellMetrics.WindowedShellLike;
    public bool FullscreenToggleVisible { get; set; }
    public bool FullscreenToggleChecked { get; set; }
    public bool SplitControlFound { get; set; }
    public List<NativeInterestingControl> LayoutSections { get; set; } = [];
    public List<NativeInterestingControl> LayoutOptions { get; set; } = [];
}

internal sealed class NativeWindowedVisualShellMetrics
{
    public bool ProbeSucceeded { get; set; }
    public bool WindowedShellLike { get; set; }
    public double WindowedShellScore { get; set; }
    public double WindowedShellLeftMean { get; set; }
    public double WindowedShellLeftStd { get; set; }
    public double WindowedShellLeftBrightRatio { get; set; }
    public double WindowedShellLeftDarkRatio { get; set; }
    public double WindowedShellTopMean { get; set; }
    public double WindowedShellTopStd { get; set; }
    public double WindowedShellTopBrightRatio { get; set; }
    public double WindowedShellTopDarkRatio { get; set; }
    public double WindowedShellPreviewMean { get; set; }
    public double WindowedShellPreviewStd { get; set; }
    public double WindowedShellPreviewBrightRatio { get; set; }
    public double WindowedShellPreviewDarkRatio { get; set; }
}

internal sealed class NativeLumaRegionMetrics
{
    public int SampleCount { get; set; }
    public double Mean { get; set; }
    public double Std { get; set; }
    public double BrightRatio { get; set; }
    public double DarkRatio { get; set; }
}

internal sealed class NativeRuntimeLayoutStateResult
{
    public bool PanelVisible { get; set; }
    public bool PanelOpened { get; set; }
    public bool PanelClosed { get; set; }
    public bool SplitControlFound { get; set; }
    public List<NativeInterestingControl> LayoutSections { get; set; } = [];
    public List<NativeInterestingControl> LayoutOptions { get; set; } = [];
    public List<NativeRuntimeLayoutOptionDescriptor> ResolvedOptions { get; set; } = [];
    public int? SelectedLayout { get; set; }
    public string? SelectedSection { get; set; }
    public string? SelectedLabel { get; set; }
    public string CloseMethod { get; set; } = string.Empty;
}

internal sealed class NativeRuntimeLayoutSelectionResult
{
    public bool Success { get; set; }
    public bool AlreadySelected { get; set; }
    public bool SelectionConfirmed { get; set; }
    public bool PanelVisible { get; set; }
    public bool PanelOpened { get; set; }
    public bool PanelClosed { get; set; }
    public NativeRuntimeLayoutOptionDescriptor? Option { get; set; }
    public int? SelectedLayout { get; set; }
    public string? SelectedSection { get; set; }
    public string? SelectedLabel { get; set; }
    public string Method { get; set; } = string.Empty;
    public string CloseMethod { get; set; } = string.Empty;
    public bool CloseFallbackUsed { get; set; }
    public Dictionary<string, int>? ClickedPoint { get; set; }
}

internal sealed class NativeRuntimeLayoutOptionDescriptor
{
    public string Section { get; set; } = string.Empty;
    public string Label { get; set; } = string.Empty;
    public RectDto Bounds { get; set; } = new();
    public bool Selected { get; set; }
    public string Source { get; set; } = string.Empty;
    public string ControlType { get; set; } = string.Empty;
}

internal sealed class NativeInterestingControlMatch
{
    [JsonIgnore]
    public AutomationElement Element { get; set; } = null!;
    public NativeInterestingControl Control { get; set; } = new();
}

internal sealed class NativeRuntimeLayoutCloseAttemptResult
{
    public bool Confirmed { get; set; }
    public string Method { get; set; } = string.Empty;
    public bool FallbackUsed { get; set; }
    public NativeRuntimeSignalsResult SignalsAfterClose { get; set; } = new();
}

internal sealed class NativeInterestingControl
{
    public string Name { get; set; } = string.Empty;
    public string ControlType { get; set; } = string.Empty;
    public RectDto Bounds { get; set; } = new();
    public string Source { get; set; } = string.Empty;
    public bool Selected { get; set; }

    public static NativeInterestingControl From(AutomationElement element, string source)
    {
        var snapshot = ElementSnapshot.From(element, IntPtr.Zero, source);
        return new NativeInterestingControl
        {
            Name = snapshot.Name,
            ControlType = snapshot.ControlType,
            Bounds = snapshot.Bounds,
            Source = source,
            Selected = ReadSelectedState(element),
        };
    }

    private static bool ReadSelectedState(AutomationElement element)
    {
        try
        {
            var toggle = element.Patterns.Toggle.PatternOrDefault;
            if (toggle is not null)
            {
                return toggle.ToggleState.ToString().Contains("On", StringComparison.OrdinalIgnoreCase);
            }
        }
        catch
        {
        }

        try
        {
            var selection = element.Patterns.SelectionItem.PatternOrDefault;
            if (selection is not null)
            {
                return selection.IsSelected;
            }
        }
        catch
        {
        }

        return false;
    }
}

internal static class NativeInputBridge
{
    public static bool PointerAction(int x, int y, bool isDoubleClick, bool restoreCursor)
    {
        var originalPoint = restoreCursor ? NativeWin32.GetCursorPosition() : null;
        NativeWin32.SetCursorPosition(x, y);
        Thread.Sleep(20);
        NativeWin32.MouseLeftClick();
        if (isDoubleClick)
        {
            Thread.Sleep(80);
            NativeWin32.MouseLeftClick();
        }
        if (restoreCursor && originalPoint is not null)
        {
            Thread.Sleep(20);
            NativeWin32.SetCursorPosition(originalPoint.Value.X, originalPoint.Value.Y);
        }
        return true;
    }

    public static bool SendEscape()
    {
        NativeWin32.KeyPress(NativeWin32.VK_ESCAPE);
        return true;
    }

    public static bool SendAltF4()
    {
        NativeWin32.KeyDown(NativeWin32.VK_MENU);
        Thread.Sleep(30);
        NativeWin32.KeyPress(NativeWin32.VK_F4, releaseAfter: false);
        Thread.Sleep(30);
        NativeWin32.KeyUp(NativeWin32.VK_F4);
        Thread.Sleep(30);
        NativeWin32.KeyUp(NativeWin32.VK_MENU);
        return true;
    }
}

internal static class NativeWin32
{
    public const byte VK_ESCAPE = 0x1B;
    public const byte VK_MENU = 0x12;
    public const byte VK_F4 = 0x73;
    public const uint InvalidColorRef = 0xFFFFFFFF;

    public static IntPtr GetForegroundWindow() => GetForegroundWindowNative();

    public static bool IsWindowVisible(IntPtr hwnd) => IsWindowVisibleNative(hwnd);

    public static bool IsIconic(IntPtr hwnd) => IsIconicNative(hwnd);

    public static int GetWindowProcessId(IntPtr hwnd)
    {
        _ = GetWindowThreadProcessId(hwnd, out var processId);
        return unchecked((int)processId);
    }

    public static string TryGetProcessName(int processId)
    {
        try
        {
            return $"{System.Diagnostics.Process.GetProcessById(processId).ProcessName}.exe";
        }
        catch
        {
            return string.Empty;
        }
    }

    public static IntPtr GetOwnerWindow(IntPtr hwnd) => GetWindow(hwnd, 4);

    public static string GetWindowTextManaged(IntPtr hwnd)
    {
        var length = GetWindowTextLength(hwnd);
        var buffer = new StringBuilder(length + 1);
        _ = GetWindowText(hwnd, buffer, buffer.Capacity);
        return buffer.ToString();
    }

    public static RectDto GetWindowRectDto(IntPtr hwnd)
    {
        if (!GetWindowRect(hwnd, out var rect))
        {
            throw new InvalidOperationException($"Failed to read window rect for hwnd={hwnd.ToInt64()}");
        }
        return new RectDto(rect.Left, rect.Top, rect.Right, rect.Bottom);
    }

    public static RectDto GetClientRectOnScreen(IntPtr hwnd)
    {
        if (!GetClientRect(hwnd, out var rect))
        {
            throw new InvalidOperationException($"Failed to read client rect for hwnd={hwnd.ToInt64()}");
        }
        var origin = new POINT { X = 0, Y = 0 };
        if (!ClientToScreen(hwnd, ref origin))
        {
            throw new InvalidOperationException($"Failed to map client rect to screen for hwnd={hwnd.ToInt64()}");
        }
        return new RectDto(origin.X, origin.Y, origin.X + rect.Right, origin.Y + rect.Bottom);
    }

    public static RectDto GetMonitorRect(IntPtr hwnd)
    {
        var monitor = MonitorFromWindow(hwnd, 2);
        var info = new MONITORINFO { cbSize = Marshal.SizeOf<MONITORINFO>() };
        if (monitor == IntPtr.Zero || !GetMonitorInfo(monitor, ref info))
        {
            throw new InvalidOperationException($"Failed to resolve monitor rect for hwnd={hwnd.ToInt64()}");
        }
        return new RectDto(info.rcMonitor.Left, info.rcMonitor.Top, info.rcMonitor.Right, info.rcMonitor.Bottom);
    }

    public static bool TryActivateWindow(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero)
        {
            return false;
        }

        var currentThreadId = GetCurrentThreadId();
        var foregroundHwnd = GetForegroundWindow();
        var foregroundThreadId = foregroundHwnd != IntPtr.Zero ? GetWindowThreadProcessId(foregroundHwnd, out _) : 0;
        var targetThreadId = GetWindowThreadProcessId(hwnd, out _);
        var attachedForeground = false;
        var attachedTarget = false;
        try
        {
            if (foregroundThreadId != 0 && foregroundThreadId != currentThreadId)
            {
                attachedForeground = AttachThreadInput(currentThreadId, foregroundThreadId, true);
            }
            if (targetThreadId != 0 && targetThreadId != currentThreadId)
            {
                attachedTarget = AttachThreadInput(currentThreadId, targetThreadId, true);
            }

            for (var attempt = 0; attempt < 4; attempt++)
            {
                if (IsIconic(hwnd))
                {
                    ShowWindow(hwnd, 9);
                    ShowWindow(hwnd, 1);
                }
                else
                {
                    ShowWindow(hwnd, 5);
                }

                BringWindowToTop(hwnd);
                SetForegroundWindow(hwnd);
                SetActiveWindow(hwnd);
                Thread.Sleep(80);
                if (GetForegroundWindow() == hwnd)
                {
                    return true;
                }
            }
        }
        finally
        {
            if (attachedTarget)
            {
                AttachThreadInput(currentThreadId, targetThreadId, false);
            }
            if (attachedForeground)
            {
                AttachThreadInput(currentThreadId, foregroundThreadId, false);
            }
        }

        return false;
    }

    public static void SetCursorPosition(int x, int y)
    {
        _ = SetCursorPos(x, y);
    }

    public static POINT? GetCursorPosition()
    {
        if (GetCursorPos(out var point))
        {
            return point;
        }
        return null;
    }

    public static IntPtr GetScreenDc() => GetDC(IntPtr.Zero);

    public static void ReleaseScreenDc(IntPtr screenDc)
    {
        if (screenDc != IntPtr.Zero)
        {
            _ = ReleaseDC(IntPtr.Zero, screenDc);
        }
    }

    public static uint GetScreenPixel(IntPtr screenDc, int x, int y) => GetPixel(screenDc, x, y);

    public static void MouseLeftClick()
    {
        mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero);
        Thread.Sleep(20);
        mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero);
    }

    public static void KeyPress(byte keyCode, bool releaseAfter = true)
    {
        keybd_event(keyCode, 0, 0, UIntPtr.Zero);
        Thread.Sleep(30);
        if (releaseAfter)
        {
            keybd_event(keyCode, 0, 0x0002, UIntPtr.Zero);
        }
    }

    public static void KeyDown(byte keyCode)
    {
        keybd_event(keyCode, 0, 0, UIntPtr.Zero);
    }

    public static void KeyUp(byte keyCode)
    {
        keybd_event(keyCode, 0, 0x0002, UIntPtr.Zero);
    }

    [DllImport("user32.dll", EntryPoint = "GetForegroundWindow")]
    private static extern IntPtr GetForegroundWindowNative();

    [DllImport("user32.dll", EntryPoint = "IsWindowVisible")]
    private static extern bool IsWindowVisibleNative(IntPtr hWnd);

    [DllImport("user32.dll", EntryPoint = "IsIconic")]
    private static extern bool IsIconicNative(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll")]
    private static extern IntPtr GetWindow(IntPtr hWnd, uint uCmd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    private static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    private static extern bool ClientToScreen(IntPtr hWnd, ref POINT lpPoint);

    [DllImport("user32.dll")]
    private static extern IntPtr MonitorFromWindow(IntPtr hwnd, uint dwFlags);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool GetMonitorInfo(IntPtr hMonitor, ref MONITORINFO lpmi);

    [DllImport("user32.dll")]
    private static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);

    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    private static extern bool BringWindowToTop(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern IntPtr SetActiveWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern bool SetCursorPos(int X, int Y);

    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out POINT lpPoint);

    [DllImport("user32.dll")]
    private static extern IntPtr GetDC(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern int ReleaseDC(IntPtr hWnd, IntPtr hDC);

    [DllImport("user32.dll")]
    private static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);

    [DllImport("user32.dll")]
    private static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);

    [DllImport("gdi32.dll")]
    private static extern uint GetPixel(IntPtr hdc, int nXPos, int nYPos);

    [StructLayout(LayoutKind.Sequential)]
    public struct POINT
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MONITORINFO
    {
        public int cbSize;
        public RECT rcMonitor;
        public RECT rcWork;
        public uint dwFlags;
    }
}

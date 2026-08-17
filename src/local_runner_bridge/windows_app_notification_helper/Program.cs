using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Windows.AppNotifications;
using Microsoft.Windows.AppNotifications.Builder;

namespace LocalAIWorkbench.NotificationHelper;

internal static class Program
{
    private const string Protocol = "lawb.windows_app_notification_helper.v1";

    private sealed class ReceiptState
    {
        internal ReceiptState(string operation)
        {
            Operation = operation;
        }

        internal string Operation { get; }
        internal string Status { get; set; } = "ambiguous";
        internal string Detail { get; set; } = "windows_app_notification_startup_incomplete";
        internal string Stage { get; set; } = "startup";
        internal string BootstrapStatus { get; set; } = "not_attempted";
        internal string RegisterStatus { get; set; } = "not_attempted";
        internal string? NotificationSetting { get; set; }
        internal bool ShowAttempted { get; set; }
        internal bool ShowReturned { get; set; }
        internal string CleanupStatus { get; set; } = "not_attempted";
        internal bool ApiSubmissionConfirmed { get; set; }
        internal string? ErrorType { get; set; }
        internal string? ErrorHResult { get; set; }
        internal string? CleanupErrorType { get; set; }
        internal string? CleanupErrorHResult { get; set; }
        internal string GetAllStatus { get; set; } = "not_attempted";
        internal int? NotificationCount { get; set; }
        internal List<object> Notifications { get; } = new();
    }

    private static async Task<int> Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] == "--validate")
            {
                return ValidatePlatform();
            }
            if (args.Length == 1 && args[0] == "--probe-registration")
            {
                return ProbeRegistration();
            }
            if (args.Length == 1 && args[0] == "--get-all")
            {
                return await GetAllNotifications();
            }

            var (title, message) = ParseSubmission(args);
            return Submit(title, message);
        }
        catch (ArgumentException error)
        {
            return WriteArgumentFailure(error);
        }
        catch (FormatException error)
        {
            return WriteArgumentFailure(error);
        }
        catch (Exception error)
        {
            var state = new ReceiptState("startup")
            {
                Detail = "windows_app_notification_startup_failed",
                Stage = "bootstrap",
                BootstrapStatus = "failed",
            };
            RecordPrimaryError(state, error);
            WriteReceipt(state);
            return 1;
        }
    }

    private static int ValidatePlatform()
    {
        var state = new ReceiptState("validate");
        if (!TryGetManager(state, out var manager))
        {
            WriteReceipt(state);
            return 3;
        }

        try
        {
            state.Stage = "setting";
            state.NotificationSetting = manager.Setting.ToString();
            state.Status = "ready";
            state.Detail = "windows_app_notifications_supported";
            state.Stage = "complete";
            WriteReceipt(state);
            return 0;
        }
        catch (Exception error)
        {
            state.Detail = "windows_app_notification_setting_failed";
            state.Stage = "setting";
            RecordPrimaryError(state, error);
            WriteReceipt(state);
            return 4;
        }
    }

    private static int ProbeRegistration()
    {
        var state = new ReceiptState("registration_probe");
        if (!TryGetManager(state, out var manager))
        {
            WriteReceipt(state);
            return 3;
        }
        if (!TryRegister(manager, state))
        {
            WriteReceipt(state);
            return 4;
        }

        var exitCode = 0;
        try
        {
            state.Stage = "setting";
            state.NotificationSetting = manager.Setting.ToString();
            state.Status = "ready";
            state.Detail = "windows_app_notification_registration_probe_completed";
        }
        catch (Exception error)
        {
            state.Detail = "windows_app_notification_setting_failed";
            state.Stage = "setting";
            RecordPrimaryError(state, error);
            exitCode = 5;
        }

        if (!TryCleanup(manager, state))
        {
            if (exitCode == 0)
            {
                state.Status = "ambiguous";
                state.Detail = "windows_app_notification_registration_probe_cleanup_failed";
                state.Stage = "cleanup";
                exitCode = 6;
            }
        }
        else if (exitCode == 0)
        {
            state.Stage = "complete";
        }

        WriteReceipt(state);
        return exitCode;
    }

    private static async Task<int> GetAllNotifications()
    {
        var state = new ReceiptState("get_all");
        if (!TryGetManager(state, out var manager))
        {
            WriteReceipt(state);
            return 3;
        }
        if (!TryRegister(manager, state))
        {
            WriteReceipt(state);
            return 4;
        }

        try
        {
            state.Stage = "setting";
            state.NotificationSetting = manager.Setting.ToString();
        }
        catch (Exception error)
        {
            state.Detail = "windows_app_notification_setting_failed";
            state.Stage = "setting";
            RecordPrimaryError(state, error);
            TryCleanup(manager, state);
            WriteReceipt(state);
            return 5;
        }

        try
        {
            state.Stage = "get_all";
            state.GetAllStatus = "started";
            var notifications = await manager.GetAllAsync();
            foreach (var notification in notifications)
            {
                var payload = notification.Payload ?? string.Empty;
                var containsLocalAIWorkbench = payload.Contains(
                    "Local AI Workbench",
                    StringComparison.Ordinal);
                var containsVerificationTitle = payload.Contains(
                    "AppNotification verification",
                    StringComparison.Ordinal);
                var containsWorkflowNode = payload.Contains(
                    "LOW-LATENCY-WORKFLOW-RESULT-NOTIFICATION-03",
                    StringComparison.Ordinal);
                var containsReviewBoundary = payload.Contains(
                    "Execution result is awaiting ChatGPT review",
                    StringComparison.Ordinal);
                state.Notifications.Add(new
                {
                    id = notification.Id,
                    tag = notification.Tag ?? string.Empty,
                    group = notification.Group ?? string.Empty,
                    payload_length = payload.Length,
                    payload_sha256 = Convert.ToHexString(
                        SHA256.HashData(Encoding.UTF8.GetBytes(payload))
                    ).ToLowerInvariant(),
                    contains_local_ai_workbench = containsLocalAIWorkbench,
                    contains_appnotification_verification = containsVerificationTitle,
                    contains_workflow_node = containsWorkflowNode,
                    contains_review_boundary = containsReviewBoundary,
                    matches_prior_smoke = containsLocalAIWorkbench
                        && containsVerificationTitle
                        && containsWorkflowNode
                        && containsReviewBoundary,
                });
            }
            state.NotificationCount = notifications.Count;
            state.GetAllStatus = "succeeded";
            state.Status = "ready";
            state.Detail = "windows_app_notification_get_all_completed";
        }
        catch (Exception error)
        {
            state.GetAllStatus = "failed";
            state.Detail = "windows_app_notification_get_all_failed";
            state.Stage = "get_all";
            RecordPrimaryError(state, error);
            TryCleanup(manager, state);
            WriteReceipt(state);
            return 6;
        }

        if (!TryCleanup(manager, state))
        {
            state.Status = "ambiguous";
            state.Detail = "windows_app_notification_get_all_cleanup_failed";
            state.Stage = "cleanup";
            WriteReceipt(state);
            return 7;
        }

        state.Stage = "complete";
        WriteReceipt(state);
        return 0;
    }

    private static int Submit(string title, string message)
    {
        var state = new ReceiptState("submit");
        if (!TryGetManager(state, out var manager))
        {
            WriteReceipt(state);
            return 3;
        }
        if (!TryRegister(manager, state))
        {
            WriteReceipt(state);
            return 4;
        }

        try
        {
            state.Stage = "setting";
            var setting = manager.Setting;
            state.NotificationSetting = setting.ToString();
            if (setting != AppNotificationSetting.Enabled)
            {
                state.Detail =
                    $"windows_app_notifications_{setting.ToString().ToLowerInvariant()}";
                TryCleanup(manager, state);
                WriteReceipt(state);
                return 5;
            }
        }
        catch (Exception error)
        {
            state.Detail = "windows_app_notification_setting_failed";
            state.Stage = "setting";
            RecordPrimaryError(state, error);
            TryCleanup(manager, state);
            WriteReceipt(state);
            return 5;
        }

        AppNotification notification;
        try
        {
            state.Stage = "build_notification";
            notification = new AppNotificationBuilder()
                .AddText(title)
                .AddText(message)
                .BuildNotification();
        }
        catch (Exception error)
        {
            state.Detail = "windows_app_notification_construction_failed";
            RecordPrimaryError(state, error);
            TryCleanup(manager, state);
            WriteReceipt(state);
            return 6;
        }

        state.Stage = "show";
        state.ShowAttempted = true;
        WriteShowAttemptedEvent(state);
        try
        {
            manager.Show(notification);
            state.ShowReturned = true;
            state.ApiSubmissionConfirmed = true;
            state.Detail = "windows_app_notification_show_returned";
        }
        catch (Exception error)
        {
            state.Detail = "windows_app_notification_show_failed";
            RecordPrimaryError(state, error);
        }

        var cleanupSucceeded = TryCleanup(manager, state);
        if (state.ShowReturned && cleanupSucceeded)
        {
            state.Status = "submitted";
            state.Stage = "complete";
            WriteReceipt(state);
            return 0;
        }
        if (state.ShowReturned)
        {
            state.Status = "ambiguous";
            state.Detail = "windows_app_notification_show_returned_cleanup_failed";
            state.Stage = "cleanup";
            WriteReceipt(state);
            return 7;
        }

        WriteReceipt(state);
        return 7;
    }

    private static bool TryGetManager(
        ReceiptState state,
        out AppNotificationManager manager)
    {
        manager = null!;
        state.Stage = "bootstrap";
        state.BootstrapStatus = "started";
        try
        {
            if (!AppNotificationManager.IsSupported())
            {
                state.BootstrapStatus = "unsupported";
                state.Detail = "windows_app_notifications_not_supported";
                return false;
            }
            manager = AppNotificationManager.Default;
            state.BootstrapStatus = "succeeded";
            return true;
        }
        catch (Exception error)
        {
            state.BootstrapStatus = "failed";
            state.Detail = "windows_app_notification_bootstrap_failed";
            RecordPrimaryError(state, error);
            return false;
        }
    }

    private static bool TryRegister(
        AppNotificationManager manager,
        ReceiptState state)
    {
        state.Stage = "register";
        try
        {
            manager.NotificationInvoked += static (_, _) => { };
            manager.Register();
            state.RegisterStatus = "succeeded";
            return true;
        }
        catch (Exception error)
        {
            state.RegisterStatus = "failed";
            state.Detail = "windows_app_notification_register_failed";
            RecordPrimaryError(state, error);
            return false;
        }
    }

    private static bool TryCleanup(
        AppNotificationManager manager,
        ReceiptState state)
    {
        if (state.RegisterStatus != "succeeded")
        {
            return true;
        }

        state.CleanupStatus = "started";
        try
        {
            manager.Unregister();
            state.CleanupStatus = "succeeded";
            return true;
        }
        catch (Exception error)
        {
            state.CleanupStatus = "failed";
            state.CleanupErrorType = error.GetType().FullName;
            state.CleanupErrorHResult = $"0x{error.HResult:X8}";
            return false;
        }
    }

    private static (string Title, string Message) ParseSubmission(string[] args)
    {
        if (
            args.Length != 4
            || args[0] != "--title-base64"
            || args[2] != "--message-base64")
        {
            throw new ArgumentException("Invalid arguments.");
        }

        var strictUtf8 = new UTF8Encoding(false, true);
        var title = strictUtf8.GetString(Convert.FromBase64String(args[1]));
        var message = strictUtf8.GetString(Convert.FromBase64String(args[3]));
        if (string.IsNullOrWhiteSpace(title) || string.IsNullOrWhiteSpace(message))
        {
            throw new ArgumentException("Notification text is required.");
        }
        return (title, message);
    }

    private static int WriteArgumentFailure(Exception error)
    {
        var state = new ReceiptState("startup")
        {
            Detail = "windows_app_notification_arguments_invalid",
            Stage = "arguments",
        };
        RecordPrimaryError(state, error);
        WriteReceipt(state);
        return 2;
    }

    private static void RecordPrimaryError(ReceiptState state, Exception error)
    {
        state.ErrorType = error.GetType().FullName;
        state.ErrorHResult = $"0x{error.HResult:X8}";
    }

    private static void WriteShowAttemptedEvent(ReceiptState state)
    {
        WritePayload("event", "show_attempted", state);
        Console.Out.Flush();
    }

    private static void WriteReceipt(ReceiptState state)
    {
        WritePayload("receipt", null, state);
        Console.Out.Flush();
    }

    private static void WritePayload(
        string recordType,
        string? eventName,
        ReceiptState state)
    {
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            protocol = Protocol,
            record_type = recordType,
            event_name = eventName,
            operation = state.Operation,
            status = state.Status,
            detail = state.Detail,
            stage = state.Stage,
            bootstrap_status = state.BootstrapStatus,
            register_status = state.RegisterStatus,
            notification_setting = state.NotificationSetting,
            show_attempted = state.ShowAttempted,
            show_returned = state.ShowReturned,
            cleanup_status = state.CleanupStatus,
            api_submission_confirmed = state.ApiSubmissionConfirmed,
            user_visible_delivery_confirmed = false,
            error_type = state.ErrorType,
            error_hresult = state.ErrorHResult,
            cleanup_error_type = state.CleanupErrorType,
            cleanup_error_hresult = state.CleanupErrorHResult,
            get_all_status = state.GetAllStatus,
            notification_count = state.NotificationCount,
            notifications = state.Notifications,
        }));
    }
}

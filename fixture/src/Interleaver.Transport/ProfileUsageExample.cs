using Interleaver.Core;
namespace Interleaver.Transport;
public static class ProfileUsageExample
{
    public static Task<bool> ConfigureDefaultAsync(DeviceController controller, CancellationToken cancellationToken = default)
    {
        var profile = new SimpleInterleaverProfile(branchCount: 4, delayStepSymbols: 8);
        return controller.ApplyInterleaverProfile(profile, cancellationToken);
    }
}

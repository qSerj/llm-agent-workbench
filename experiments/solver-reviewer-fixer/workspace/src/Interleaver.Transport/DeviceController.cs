using Interleaver.Core;
namespace Interleaver.Transport;

public sealed class DeviceController
{
    private const byte ApplyInterleaverCommand = 0x42;
    private readonly IRegisterTransport _transport;
    private int[]? _lastAppliedRegisters;
    public DeviceController(IRegisterTransport transport) => _transport = transport;
    public async Task<bool> ApplyInterleaverProfile(IInterleaverProfile profile, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(profile);
        var registers = profile.ToRegisters().ToArray();
        if (_lastAppliedRegisters is not null && _lastAppliedRegisters.SequenceEqual(registers)) return false;
        await _transport.WriteAsync(ApplyInterleaverCommand, registers, cancellationToken);
        _lastAppliedRegisters = registers;
        return true;
    }
}

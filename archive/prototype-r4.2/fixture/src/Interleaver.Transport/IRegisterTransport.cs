namespace Interleaver.Transport;
public interface IRegisterTransport
{
    Task WriteAsync(byte command, IReadOnlyList<int> registers, CancellationToken cancellationToken);
}

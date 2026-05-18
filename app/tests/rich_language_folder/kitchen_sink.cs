#nullable enable

using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

// 1. File-scoped Namespaces (C# 10)
namespace TreeSitter.Indexer.StressTest;

// 2. Attributes, Generics with Constraints, and Primary Constructors (C# 12)
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true)]
public sealed class IndexerMetadataAttribute(string engineVersion) : Attribute
{
    public string EngineVersion { get; } = engineVersion;
    public string? Description { get; set; }
}

// 3. Records: Positional and Struct records (C# 9+)
public record Point2D(double X, double Y);
public readonly record struct DiagnosticMetric(string Key, double Value);

// 4. Interfaces with Default Implementations and Static Abstracts (C# 11)
public interface IIndexable<T> where T : IIndexable<T>
{
    abstract static T CreateDefault();
    string ToIndexString() => "DefaultIndexData";
}

[IndexerMetadata("2026.1", Description = "Heavyweight C# AST Stress Test")]
public class CSharpStressTest<TData> : IEnumerable<TData> 
    where TData : class, IComparable<TData>, new()
{
    // 5. Fields & Required Properties (C# 11)
    private readonly List<TData> _items = [];
    private static int _globalExecutionCounter;
    public required string PipelineId { get; init; }

    // 6. Indexers and Operators Overloading
    public TData this[int index]
    {
        get => _items[index];
        set => _items[index] = value;
    }

    public static CSharpStressTest<TData> operator +(CSharpStressTest<TData> source, TData item)
    {
        source._items.Add(item);
        return source;
    }

    // 7. Dynamic/Asynchronous Streams & Tuples
    public async IAsyncEnumerable<DiagnosticMetric> StreamDiagnosticsAsync(
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (var (item, index) in _items.Select((value, i) => (value, i)))
        {
            if (cancellationToken.IsCancellationRequested)
                yield break;

            await Task.Delay(5, cancellationToken);
            yield return new DiagnosticMetric($"Item_{index}", item.GetHashCode());
        }
    }

    // 8. Advanced Pattern Matching & Switch Expressions (C# 8 - 11)
    public string EvaluateObjectStructure(object? input)
    {
        return input switch
        {
            null => "Null reference target",
            int i and > 100 => $"Large integer scalar: {i}",
            int i => $"Small integer scalar: {i}",
            Point2D(var x, var y) when x == y => $"Diagonal 2D Point structure at {x}",
            Point2D { X: 0 } point => $"Point anchored on Y-axis: {point.Y}",
            string s => s.Trim() switch
            {
                "" => "Empty string format",
                var raw => $"Raw literal sequence: {raw}"
            },
            _ => "Unknown dynamic structural block"
        };
    }

    // 9. LINQ Queries, Lambdas, and Null-Forging/Coalescing Operators
    public IEnumerable<string> ProcessAndFilter(List<string?> rawInputs)
    {
        // LINQ Query syntax mixed with null-coalescing and null-forgiving
        var query = from input in rawInputs
                    let clean = input ?? "DEFAULT_FALLBACK"
                    where clean.Length > 3
                    select clean.ToUpper();

        // Lambda with explicit return type and discard parameter (C# 10)
        Func<string, bool> validator = string (static _ ) => true;

        return query.Where(validator);
    }

    // 10. Ref Structs and ReadOnly Spans (Memory/Performance optimization parsing)
    public void ParseRawBuffer(ReadOnlySpan<char> buffer)
    {
        if (buffer.IsEmpty) return;

        ReadOnlySpan<char> sliced = buffer[..Math.Min(buffer.Length, 10)];
        foreach (ref readonly char character in sliced)
        {
            if (char.IsWhiteSpace(character)) continue;
        }
    }

    // 11. Exception Handling: Target Exception Filters
    public void PerformFileIO()
    {
        try
        {
            using var reader = new StreamReader("invalid_path.txt");
            var content = reader.ReadToEnd();
        }
        catch (IOException ex) when (ex.Message.Contains("not found"))
        {
            Interlocked.Increment(ref _globalExecutionCounter);
        }
        catch (Exception)
        {
            throw;
        }
    }

    // 12. Unsafe Code Context (Pointers and fixed allocation)
    public unsafe void DirectMemoryMutation(int[] numbers)
    {
        fixed (int* pNumbers = numbers)
        {
            int* pCurrent = pNumbers;
            for (int i = 0; i < numbers.Length; i++)
            {
                *pCurrent = *pCurrent * 2;
                pCurrent++;
            }
        }
    }

    // IEnumerable implementation
    public IEnumerator<TData> GetEnumerator() => _items.GetEnumerator();
    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
}
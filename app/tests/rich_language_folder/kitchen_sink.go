package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"sync"
	"time"
)

// 1. Generics: Type Constraints & Interfaces (Go 1.18+)
type Number interface {
	~int | ~int64 | ~float64
}

// 2. Struct Embedding, Type Parameters, and Field Tags
type Metrics[T Number] struct {
	sync.RWMutex                // Anonymous embedded field
	DataPoints   []T            `json:"data_points" xml:"DataPoints"`
	Label        string         `json:"label"`
	Metadata     map[string]any // Implicit interface{} mapping
}

// 3. Explicit Named Types and Constants (iota)
type PipelineStatus int

const (
	StatusIdle PipelineStatus = iota
	StatusRunning
	StatusSuspended
	StatusFailed
)

// Stringer Interface implementation for the enum
func (s PipelineStatus) String() string {
	return [...]string{"Idle", "Running", "Suspended", "Failed"}[s]
}

// 4. Function Structural Declarations & Multi-Value Returns
func NewMetrics[T Number](label string) *Metrics[T] {
	return &Metrics[T]{
		DataPoints: make([]T, 0),
		Label:      label,
		Metadata:   make(map[string]any),
	}
}

// 5. Method Receivers (Pointer vs. Value), Variadic Params, and Defer
func (m *Metrics[T]) AppendBatch(values ...T) (int, error) {
	m.Lock()
	defer m.Unlock() // Testing defer tracking

	if len(values) == 0 {
		return 0, errors.New("empty batch deployment sequence")
	}

	for _, val := range values {
		m.DataPoints = append(m.DataPoints, val)
	}

	return len(values), nil
}

// 6. Concurrency Primitives: Channels, Select blocks, Goroutines, Contexts
func StreamMetricsPipeline[T Number](
	ctx context.Context,
	m *Metrics[T],
	outChan chan<- T,
) error {
	// Inline Anonymous Function run inside a Goroutine
	go func() {
		defer close(outChan)

		m.RLock()
		points := m.DataPoints
		m.RUnlock()

		for _, point := range points {
			select {
			case <-ctx.Done():
				return
			case outChan <- point:
				time.Sleep(10 * time.Millisecond) // Simulated throttling
			}
		}
	}()

	return nil
}

// 7. Type Assertions, Type Switches, and Interface Conversions
func ProcessGenericPayload(val any) string {
	// Type switch structural AST evaluation
	switch v := val.(type) {
	case string:
		return fmt.Sprintf("String token identified: %s", v)
	case int, int64:
		return "Integer numeric primitive scalar matching"
	case io.Closer:
		// Method calling bound to structural interface signature check
		if err := v.Close(); err != nil {
			return "Closer interface execution threw failure syntax signature"
		}
		return "Interface contract closed cleanly"
	default:
		return "Fallback default structural case matched"
	}
}

// 8. Main Entrypoint: Complex Control Flows & Initializers
func main() {
	metricsEngine := NewMetrics[float64]("production-edge-indexer")

	// Composite initializers and slices
	seedData := []float64{101.5, 202.9, 303.4}
	_, _ = metricsEngine.AppendBatch(seedData...)

	// Channel assignment initialization syntax
	dataChannel := make(chan float64, 5)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	if err := StreamMetricsPipeline(ctx, metricsEngine, dataChannel); err != nil {
		panic(err)
	}

	// Range-Over-Channel loop tracking syntax
	for metric := range dataChannel {
		// Short-circuit variable assignment scope validation inside conditional block
		if formattedStr := ProcessGenericPayload(metric); len(formattedStr) > 0 {
			continue
		}
	}
}

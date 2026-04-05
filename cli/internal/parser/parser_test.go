package parser

import (
	"math"
	"testing"
)

func TestNormalizeNumber(t *testing.T) {
	tests := []struct {
		name string
		in   interface{}
		want *float64
	}{
		{"nil", nil, nil},
		{"bool", true, nil},
		{"empty string", "", nil},
		{"dash", "--", nil},
		{"N/A", "N/A", nil},
		{"int", 42, ptr(42.0)},
		{"float", 3.14, ptr(3.14)},
		{"NaN", math.NaN(), nil},
		{"Inf", math.Inf(1), nil},
		{"simple", "100", ptr(100.0)},
		{"K suffix", "1.5K", ptr(1500.0)},
		{"M suffix", "951.89M", ptr(951_890_000.0)},
		{"B suffix", "2.41B", ptr(2_410_000_000.0)},
		{"T suffix", "1T", ptr(1_000_000_000_000.0)},
		{"with commas", "1,234.56", ptr(1234.56)},
		{"with dollar", "$100", ptr(100.0)},
		{"with USDT", "100USDT", ptr(100.0)},
		{"negative", "-5.5M", ptr(-5_500_000.0)},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := NormalizeNumber(tt.in)
			if tt.want == nil {
				if got != nil {
					t.Errorf("got %v, want nil", *got)
				}
				return
			}
			if got == nil {
				t.Fatalf("got nil, want %v", *tt.want)
			}
			if math.Abs(*got-*tt.want) > 0.01 {
				t.Errorf("got %v, want %v", *got, *tt.want)
			}
		})
	}
}

func TestParseOverviewPayload(t *testing.T) {
	payload := map[string]interface{}{
		"data": map[string]interface{}{
			"longTradersQty":          "951.89M",
			"shortTradersQty":         "780M",
			"longTradersAvgEntryPrice": 42100.5,
			"shortTradersAvgEntryPrice": 42200.75,
		},
	}

	result := ParseOverviewPayload(payload, "trader")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result.Long.PositionQty == nil || math.Abs(*result.Long.PositionQty-951_890_000) > 1 {
		t.Errorf("long qty = %v", result.Long.PositionQty)
	}
	if result.Short.PositionQty == nil || math.Abs(*result.Short.PositionQty-780_000_000) > 1 {
		t.Errorf("short qty = %v", result.Short.PositionQty)
	}
}

func TestParseOverviewPayloadWhale(t *testing.T) {
	payload := map[string]interface{}{
		"data": map[string]interface{}{
			"longWhalesQty":  100.5,
			"shortWhalesQty": 80.0,
		},
	}

	result := ParseOverviewPayload(payload, "whale")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result.Long.PositionQty == nil || *result.Long.PositionQty != 100.5 {
		t.Errorf("long qty = %v", result.Long.PositionQty)
	}
}

func ptr(f float64) *float64 { return &f }

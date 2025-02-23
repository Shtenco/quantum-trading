import MetaTrader5 as mt5
import numpy as np
from qiskit import QuantumCircuit, transpile, QuantumRegister, ClassicalRegister
from qiskit_aer import AerSimulator
from qiskit.visualization import plot_histogram
from Crypto.Hash import SHA256
import pandas as pd
from datetime import datetime, timedelta

def initialize_mt5():
    if not mt5.initialize():
        print("MT5 initialization error")
        return False
    return True

def get_price_data(symbol="EURUSD", timeframe=mt5.TIMEFRAME_D1, n_candles=256, offset=0):
    """Retrieves price data from MT5"""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, offset, n_candles)
    if rates is None:
        return None
    return pd.DataFrame(rates)

def prices_to_binary(df):
    """Converts price movements into a binary sequence"""
    binary_sequence = ""
    for i in range(1, len(df)):
        binary_sequence += "1" if df['close'][i] > df['close'][i-1] else "0"
    return binary_sequence.zfill(256)

def calculate_future_horizon(current_data, future_data, horizon=10):
    """Calculates the binary horizon of future prices"""
    future_binary = ""
    current_price = current_data['close'].iloc[-1]

    for price in future_data['close']:
        future_binary += "1" if price > current_price else "0"
        current_price = price

    return future_binary.zfill(horizon)

def calculate_trend_ratio(binary_sequence):
    """Calculates the ratio of 1/0 in a binary sequence"""
    ones = binary_sequence.count('1')
    zeros = binary_sequence.count('0')
    total = len(binary_sequence)
    return ones/total, zeros/total

def predict_horizon(quantum_counts, horizon=10):
    """Predicts the binary horizon based on the top-10 most probable states"""
    total_counts = sum(quantum_counts.values())
    # Get the top-10 states with the highest probability
    top_10_states = sorted(quantum_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    predicted_binary = ""

    # For each position in the horizon
    for i in range(horizon):
        weighted_ones = 0
        weighted_zeros = 0

        # Calculate weighted probabilities for each state
        for state, count in top_10_states:
            if len(state) > i:
                weight = count / total_counts
                if state[i] == '1':
                    weighted_ones += weight
                else:
                    weighted_zeros += weight

        # Determine the bit based on weighted probabilities
        predicted_binary += "1" if weighted_ones > weighted_zeros else "0"

    return predicted_binary

def predict_trend(binary_sequence):
    """Predicts the trend based on the 1/0 ratio"""
    ones_ratio, zeros_ratio = calculate_trend_ratio(binary_sequence)
    return "BULL" if ones_ratio > 0.5 else "BEAR"

def verify_prediction(current_data, future_data):
    """Verifies the accuracy of the prediction"""
    actual_trend = "BULL" if future_data['close'].iloc[-1] > current_data['close'].iloc[-1] else "BEAR"
    return actual_trend

def sha256_to_binary(input_data):
    hasher = SHA256.new()
    hasher.update(input_data)
    return bin(int(hasher.hexdigest(), 16))[2:].zfill(256)

def qpe_dlog(a, N, num_qubits):
    qr = QuantumRegister(num_qubits + 1)
    cr = ClassicalRegister(num_qubits)
    qc = QuantumCircuit(qr, cr)

    for q in range(num_qubits):
        qc.h(q)
    qc.x(num_qubits)

    for q in range(num_qubits):
        qc.cp(2 * np.pi * (a**(2**q) % N) / N, q, num_qubits)

    qc.barrier()
    for i in range(num_qubits):
        qc.h(i)
        for j in range(i):
            qc.cp(-np.pi / float(2 ** (i - j)), j, i)

    for i in range(num_qubits // 2):
        qc.swap(i, num_qubits - 1 - i)

    qc.measure(range(num_qubits), range(num_qubits))
    return qc

def analyze_market_state(price_binary, num_qubits=22):
    a = 70000000
    N = 17000000

    qc = qpe_dlog(a, N, num_qubits)
    simulator = AerSimulator()
    compiled_circuit = transpile(qc, simulator)
    job = simulator.run(compiled_circuit, shots=3000)
    result = job.result()
    counts = result.get_counts()

    best_match = max(counts, key=counts.get)
    dlog_value = int(best_match, 2)
    return dlog_value, counts

def compare_horizons(real_horizon, predicted_horizon):
    """
    Compares the direction of the real and predicted horizons
    Calculates the predominant direction (more 1s or 0s) and compares them
    """
    # Count the number of 1s in the real and predicted horizons
    real_ones = real_horizon.count('1')
    pred_ones = predicted_horizon.count('1')

    # Determine the predominant direction
    real_trend = "BULL" if real_ones > len(real_horizon)/2 else "BEAR"
    pred_trend = "BULL" if pred_ones > len(predicted_horizon)/2 else "BEAR"

    return "WIN" if real_trend == pred_trend else "LOSS"

def analyze_from_point(timepoint_offset, n_candles=256, horizon_length=10):
    """
    Analyzes the market from a given point in the past
    timepoint_offset - number of candles back from the current moment
    """
    try:
        # Get historical data up to the event horizon point
        historical_data = get_price_data(n_candles=n_candles, offset=timepoint_offset + horizon_length)
        if historical_data is None:
            print("Failed to retrieve historical data")
            return

        # Get real data after the point (for prediction verification)
        future_data = get_price_data(n_candles=horizon_length, offset=timepoint_offset)
        if future_data is None:
            print("Failed to retrieve verification data")
            return

        # Determine the event horizon point
        horizon_point_price = historical_data['close'].iloc[-1]
        horizon_point_time = historical_data.index[-1] if isinstance(historical_data.index, pd.DatetimeIndex) else None

        print(f"\n=== ANALYSIS FROM EVENT HORIZON POINT ===")
        print(f"Price at event horizon point: {horizon_point_price:.5f}")
        if horizon_point_time:
            print(f"Time of event horizon point: {horizon_point_time}")

        # Convert historical prices into a binary sequence
        price_binary = prices_to_binary(historical_data)
        print("\nBinary price sequence before event horizon (last 64 bits):")
        print(price_binary[-64:])

        # Analyze the market state
        market_state, quantum_counts = analyze_market_state(price_binary)

        # Display the matrix of probable projections
        print("\nMatrix of probable projections (top-20 states):")
        print("{:<22} {:<10} {:<10}".format("State", "Frequency", "Probability"))
        print("-" * 42)

        total_shots = sum(quantum_counts.values())
        sorted_states = sorted(quantum_counts.items(), key=lambda x: x[1], reverse=True)

        for state, count in sorted_states[:20]:
            probability = count / total_shots * 100
            print("{:<22} {:<10} {:.2f}%".format(state, count, probability))

        # Get the real and predicted horizons
        real_horizon = calculate_future_horizon(historical_data, future_data, horizon_length)
        predicted_horizon = predict_horizon(quantum_counts, horizon_length)

        print("\n=== COMPARISON OF PREDICTION WITH REALITY ===")
        print("Real horizon after the point:")
        print(real_horizon)
        print("\nPredicted horizon of future prices:")
        print(predicted_horizon)

        # Compare the directions of the horizons
        result = compare_horizons(real_horizon, predicted_horizon)
        horizon_accuracy = sum(a == b for a, b in zip(real_horizon, predicted_horizon)) / horizon_length

        print(f"\nNumber of 1s in the real horizon: {real_horizon.count('1')}/{len(real_horizon)}")
        print(f"Number of 1s in the prediction: {predicted_horizon.count('1')}/{len(predicted_horizon)}")
        print(f"Bit match accuracy: {horizon_accuracy:.2%}")
        print(f"Direction comparison result: {result}")

        # Analyze the probability distribution
        print("\nAnalysis of probability distribution for event horizon bits:")
        print("{:<5} {:<10} {:<10} {:<10}".format("Bit", "Prob.1", "Prob.0", "Prediction"))
        print("-" * 35)

        for i in range(horizon_length):
            weighted_ones = 0
            weighted_zeros = 0

            # Calculate weighted probabilities for the top-10 states
            for state, count in sorted_states[:10]:
                if len(state) > i:
                    weight = count / total_shots
                    if state[i] == '1':
                        weighted_ones += weight
                    else:
                        weighted_zeros += weight

            predicted_bit = "1" if weighted_ones > weighted_zeros else "0"
            print("{:<5} {:<10.2%} {:<10.2%} {:<10}".format(
                i+1, weighted_ones, weighted_zeros, predicted_bit
            ))

    except Exception as e:
        print(f"Error during analysis: {str(e)}")

def main():
    if not initialize_mt5():
        return

    try:
        # Request the event horizon point offset
        offset = int(input("Enter the event horizon point offset (number of candles back from the current moment): "))
        horizon_length = int(input("Enter the event horizon length (default is 10): ") or "10")

        # Perform analysis from the given point
        analyze_from_point(offset, horizon_length=horizon_length)

    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()

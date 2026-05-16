package com.company.service;

import java.math.BigDecimal;
import java.util.List;
import java.util.ArrayList;


public class LoanService {

    private static final BigDecimal MAX_LOAN_AMOUNT = new BigDecimal("1000000");
    private static final BigDecimal MIN_INTEREST_RATE = new BigDecimal("0.01");

    public BigDecimal calculateInterest(BigDecimal principal, BigDecimal rate, int months) {
        if (principal == null || rate == null || months <= 0) {
            throw new IllegalArgumentException("Invalid loan parameters");
        }
        return principal.multiply(rate).multiply(new BigDecimal(months));
    }

    public BigDecimal calculateMonthlyPayment(BigDecimal principal, BigDecimal annualRate, int termMonths) {
        BigDecimal monthlyRate = annualRate.divide(new BigDecimal("12"), 10, BigDecimal.ROUND_HALF_UP);
        BigDecimal onePlusR = BigDecimal.ONE.add(monthlyRate);
        BigDecimal pow = onePlusR.pow(termMonths);
        return principal.multiply(monthlyRate).multiply(pow)
                .divide(pow.subtract(BigDecimal.ONE), 2, BigDecimal.ROUND_HALF_UP);
    }

    public boolean validateLoan(BigDecimal amount, BigDecimal rate) {
        if (amount == null || rate == null) return false;
        if (amount.compareTo(BigDecimal.ZERO) <= 0) return false;
        if (amount.compareTo(MAX_LOAN_AMOUNT) > 0) return false;
        if (rate.compareTo(MIN_INTEREST_RATE) < 0) return false;
        return true;
    }

    public List<String> getValidationErrors(BigDecimal amount, BigDecimal rate, int termMonths) {
        List<String> errors = new ArrayList<>();
        if (amount == null || amount.compareTo(BigDecimal.ZERO) <= 0)
            errors.add("Loan amount must be positive");
        if (amount != null && amount.compareTo(MAX_LOAN_AMOUNT) > 0)
            errors.add("Loan amount exceeds maximum of " + MAX_LOAN_AMOUNT);
        if (rate == null || rate.compareTo(MIN_INTEREST_RATE) < 0)
            errors.add("Interest rate must be at least " + MIN_INTEREST_RATE);
        if (termMonths <= 0)
            errors.add("Loan term must be at least 1 month");
        return errors;
    }

    public BigDecimal calculatePenalty(BigDecimal outstanding, int daysOverdue) {
        if (daysOverdue <= 0) return BigDecimal.ZERO;
        BigDecimal dailyPenaltyRate = new BigDecimal("0.001");
        return outstanding.multiply(dailyPenaltyRate)
                .multiply(new BigDecimal(daysOverdue))
                .setScale(2, BigDecimal.ROUND_HALF_UP);
    }
}

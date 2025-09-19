"""
Fast batch validation for bulk portfolio operations.

This module provides optimized batch validation functions with set-based
duplicate detection and early exit logic for common failure cases.
"""

from typing import List, Set, Dict, Tuple, Optional
from app.schemas import PortfolioPostDTO
from app.validation_cache import (
    get_validation_cache, 
    generate_batch_key,
    validate_portfolio_names_format
)
from app.logging_config import get_logger
from datetime import datetime, UTC
import time

logger = get_logger(__name__)


class ValidationResult:
    """Result of batch validation with detailed error information."""
    
    def __init__(self):
        self.is_valid = True
        self.errors: List[str] = []
        self.invalid_names: List[str] = []
        self.duplicate_names: List[str] = []
        self.validation_time_ms: float = 0.0
    
    def add_error(self, error: str) -> None:
        """Add an error and mark validation as failed."""
        self.is_valid = False
        self.errors.append(error)
    
    def add_invalid_name(self, name: str) -> None:
        """Add an invalid name."""
        self.invalid_names.append(name)
        self.add_error(f"Invalid name format: {name}")
    
    def add_duplicate_name(self, name: str) -> None:
        """Add a duplicate name."""
        if name not in self.duplicate_names:
            self.duplicate_names.append(name)
        self.add_error(f"Duplicate name: {name}")
    
    def get_summary(self) -> str:
        """Get a summary of validation errors."""
        if self.is_valid:
            return "Validation passed"
        
        summary_parts = []
        if self.invalid_names:
            summary_parts.append(f"{len(self.invalid_names)} invalid names")
        if self.duplicate_names:
            summary_parts.append(f"{len(self.duplicate_names)} duplicate names")
        
        return f"Validation failed: {', '.join(summary_parts)}"


def validate_portfolio_batch(portfolio_dtos: List[PortfolioPostDTO]) -> ValidationResult:
    """
    Fast batch validation for bulk portfolio operations.
    
    Implements:
    - Set-based duplicate detection for O(n) performance
    - Early exit validation logic for common failure cases
    - Cached name format validation
    - Comprehensive error reporting
    
    Args:
        portfolio_dtos: List of PortfolioPostDTO objects to validate
        
    Returns:
        ValidationResult with validation status and detailed errors
    """
    start_time = time.perf_counter()
    result = ValidationResult()
    
    # Early exit for empty or oversized batches
    if not portfolio_dtos:
        result.add_error("Request must contain at least 1 portfolio")
        result.validation_time_ms = (time.perf_counter() - start_time) * 1000
        return result
    
    if len(portfolio_dtos) > 100:
        result.add_error("Request cannot contain more than 100 portfolios")
        result.validation_time_ms = (time.perf_counter() - start_time) * 1000
        return result
    
    # Check if we have cached validation for this exact batch
    cache = get_validation_cache()
    batch_key = generate_batch_key(portfolio_dtos)
    cached_result = cache.get_cached_batch_validation(batch_key)
    
    if cached_result is not None:
        result.is_valid = cached_result
        if not cached_result:
            result.add_error("Batch validation failed (cached result)")
        result.validation_time_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(f"Used cached batch validation: {batch_key} -> {cached_result}")
        return result
    
    # Extract names for validation
    names = [dto.name for dto in portfolio_dtos]
    
    # Fast name format validation using cache
    valid_names, invalid_names = validate_portfolio_names_format(names)
    
    # Add invalid names to result
    for name in invalid_names:
        result.add_invalid_name(name)
    
    # Early exit if name format validation failed
    if invalid_names:
        cache.cache_batch_validation_result(batch_key, False)
        result.validation_time_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(f"Batch validation failed on name format: {len(invalid_names)} invalid names")
        return result
    
    # Fast duplicate detection using set-based approach
    duplicates = find_duplicates_fast(names)
    
    # Add duplicate names to result
    for name in duplicates:
        result.add_duplicate_name(name)
    
    # Early exit if duplicates found
    if duplicates:
        cache.cache_batch_validation_result(batch_key, False)
        result.validation_time_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(f"Batch validation failed on duplicates: {len(duplicates)} duplicate names")
        return result
    
    # Additional validation checks
    validation_errors = validate_portfolio_fields_fast(portfolio_dtos)
    for error in validation_errors:
        result.add_error(error)
    
    # Cache the validation result
    cache.cache_batch_validation_result(batch_key, result.is_valid)
    
    result.validation_time_ms = (time.perf_counter() - start_time) * 1000
    
    if result.is_valid:
        logger.debug(f"Batch validation passed: {len(portfolio_dtos)} portfolios in {result.validation_time_ms:.2f}ms")
    else:
        logger.debug(f"Batch validation failed: {result.get_summary()} in {result.validation_time_ms:.2f}ms")
    
    return result


def find_duplicates_fast(names: List[str]) -> List[str]:
    """
    Fast duplicate detection using set-based approach for O(n) performance.
    
    Args:
        names: List of portfolio names to check for duplicates
        
    Returns:
        List of duplicate names (original case preserved)
    """
    if not names:
        return []
    
    seen_normalized: Set[str] = set()
    duplicates: List[str] = []
    name_mapping: Dict[str, str] = {}  # normalized -> original
    
    for name in names:
        # Normalize name for comparison (strip whitespace, lowercase)
        normalized_name = name.strip().lower()
        
        if normalized_name in seen_normalized:
            # Found duplicate - use original case from first occurrence
            original_name = name_mapping.get(normalized_name, name)
            if original_name not in duplicates:
                duplicates.append(original_name)
        else:
            seen_normalized.add(normalized_name)
            name_mapping[normalized_name] = name
    
    return duplicates


def validate_portfolio_fields_fast(portfolio_dtos: List[PortfolioPostDTO]) -> List[str]:
    """
    Fast validation of portfolio fields with early exit logic.
    
    Args:
        portfolio_dtos: List of PortfolioPostDTO objects to validate
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    for i, dto in enumerate(portfolio_dtos):
        # Validate name is not empty after stripping
        if not dto.name or not dto.name.strip():
            errors.append(f"Portfolio {i}: Name cannot be empty")
            continue  # Skip further validation for this portfolio
        
        # Validate version if provided
        if dto.version is not None and dto.version < 1:
            errors.append(f"Portfolio {i} ({dto.name}): Version must be >= 1")
        
        # Validate dateCreated if provided
        if dto.dateCreated is not None:
            try:
                # Ensure it's a valid datetime and not in the future
                if dto.dateCreated > datetime.now(UTC):
                    errors.append(f"Portfolio {i} ({dto.name}): Date created cannot be in the future")
            except (TypeError, ValueError) as e:
                errors.append(f"Portfolio {i} ({dto.name}): Invalid date format")
        
        # Early exit if we have too many errors (performance optimization)
        if len(errors) >= 10:
            errors.append(f"Too many validation errors (showing first 10)")
            break
    
    return errors


def validate_batch_size_constraints(portfolio_dtos: List[PortfolioPostDTO]) -> List[str]:
    """
    Validate batch size constraints with early exit.
    
    Args:
        portfolio_dtos: List of PortfolioPostDTO objects to validate
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    if not portfolio_dtos:
        errors.append("Request must contain at least 1 portfolio")
        return errors
    
    if len(portfolio_dtos) > 100:
        errors.append("Request cannot contain more than 100 portfolios")
        return errors
    
    # Check for reasonable name lengths in batch
    total_name_length = sum(len(dto.name) for dto in portfolio_dtos if dto.name)
    if total_name_length > 10000:  # Reasonable limit for batch processing
        errors.append("Total name length in batch exceeds reasonable limits")
    
    return errors


def validate_portfolio_batch_comprehensive(
    portfolio_dtos: List[PortfolioPostDTO],
    check_duplicates: bool = True,
    check_format: bool = True,
    check_fields: bool = True
) -> ValidationResult:
    """
    Comprehensive batch validation with configurable checks.
    
    Args:
        portfolio_dtos: List of PortfolioPostDTO objects to validate
        check_duplicates: Whether to check for duplicate names
        check_format: Whether to check name format
        check_fields: Whether to check field validation
        
    Returns:
        ValidationResult with validation status and detailed errors
    """
    start_time = time.perf_counter()
    result = ValidationResult()
    
    # Basic size constraints (always checked)
    size_errors = validate_batch_size_constraints(portfolio_dtos)
    for error in size_errors:
        result.add_error(error)
    
    # Early exit if size validation failed
    if size_errors:
        result.validation_time_ms = (time.perf_counter() - start_time) * 1000
        return result
    
    # Name format validation (if enabled)
    if check_format:
        names = [dto.name for dto in portfolio_dtos]
        valid_names, invalid_names = validate_portfolio_names_format(names)
        
        for name in invalid_names:
            result.add_invalid_name(name)
        
        # Early exit if format validation failed
        if invalid_names:
            result.validation_time_ms = (time.perf_counter() - start_time) * 1000
            return result
    
    # Duplicate detection (if enabled)
    if check_duplicates:
        names = [dto.name for dto in portfolio_dtos]
        duplicates = find_duplicates_fast(names)
        
        for name in duplicates:
            result.add_duplicate_name(name)
        
        # Early exit if duplicates found
        if duplicates:
            result.validation_time_ms = (time.perf_counter() - start_time) * 1000
            return result
    
    # Field validation (if enabled)
    if check_fields:
        field_errors = validate_portfolio_fields_fast(portfolio_dtos)
        for error in field_errors:
            result.add_error(error)
    
    result.validation_time_ms = (time.perf_counter() - start_time) * 1000
    
    if result.is_valid:
        logger.debug(f"Comprehensive batch validation passed: {len(portfolio_dtos)} portfolios in {result.validation_time_ms:.2f}ms")
    else:
        logger.debug(f"Comprehensive batch validation failed: {result.get_summary()} in {result.validation_time_ms:.2f}ms")
    
    return result


# Convenience functions for common validation scenarios
def validate_names_only(names: List[str]) -> Tuple[bool, List[str]]:
    """
    Fast validation for names only (format + duplicates).
    
    Args:
        names: List of portfolio names to validate
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    # Check format using cache
    valid_names, invalid_names = validate_portfolio_names_format(names)
    if invalid_names:
        errors.extend([f"Invalid name format: {name}" for name in invalid_names])
    
    # Check duplicates
    duplicates = find_duplicates_fast(names)
    if duplicates:
        errors.extend([f"Duplicate name: {name}" for name in duplicates])
    
    return len(errors) == 0, errors


def validate_for_database_insert(portfolio_dtos: List[PortfolioPostDTO]) -> ValidationResult:
    """
    Validation specifically optimized for database insert operations.
    
    Args:
        portfolio_dtos: List of PortfolioPostDTO objects to validate
        
    Returns:
        ValidationResult optimized for database operations
    """
    # Use comprehensive validation with all checks enabled
    return validate_portfolio_batch_comprehensive(
        portfolio_dtos,
        check_duplicates=True,
        check_format=True,
        check_fields=True
    )
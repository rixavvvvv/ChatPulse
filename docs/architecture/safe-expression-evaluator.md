89# Safe Expression Evaluator Architecture

## Overview

The Safe Expression Evaluator provides secure, AST-based expression evaluation for workflow conditions. It replaces the previously used unsafe `eval()` approach with a properly sandboxed evaluator that prevents code injection attacks.

## Design Goals

1. **Security**: Prevent code execution, imports, attribute traversal, and arbitrary function calls
2. **Expressiveness**: Support common workflow conditions (equals, greater than, contains, and/or/not)
3. **Performance**: Sub-millisecond evaluation with metrics collection
4. **Observability**: Error logging, execution metrics, and malicious attempt detection

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Expression Evaluator                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │  Input       │    │  AST Parser  │    │   AST        │     │
│  │  Expression  │───▶│  (ast.parse) │───▶│  Validator   │     │
│  │  + Context   │    └──────────────┘    └──────────────┘     │
│  └──────────────┘           │                   │             │
│                              │                   ▼             │
│                              │          ┌──────────────┐       │
│                              └─────────▶│   SafeAST    │       │
│                                         │   Visitor    │       │
│                                         └──────────────┘       │
│                                                │                │
│                                                ▼                │
│                                         ┌──────────────┐       │
│                                         │   Result     │       │
│                                         │   (bool)     │       │
│                                         └──────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. ExpressionEvaluator (`expression_evaluator.py`)

Main class that orchestrates safe evaluation:

```python
evaluator = ExpressionEvaluator()
result = evaluator.evaluate("status == 'active' and priority > 5", {
    "status": "active",
    "priority": 10
})
```

**Key methods:**
- `evaluate(expression, context)` - Parse and evaluate expression
- `_check_malicious(expression)` - Pre-check for dangerous patterns
- `_validate_ast(tree)` - Validate AST doesn't contain disallowed nodes

### 2. SafeASTVisitor

AST visitor that safely evaluates expressions by implementing only allowed operations:

- **BoolOp** (and/or) - Logical operations
- **UnaryOp** (not) - Negation
- **Compare** (==, !=, >, <, >=, <=, in, not in) - Comparisons
- **Constant** - Literals (numbers, strings, booleans)
- **Name** - Variable lookup from context
- **List/Tuple** - Collection literals

**Blocked operations:**
- `Call` - Function calls
- `Attribute` - Attribute access (e.g., `obj.attr`)
- `Lambda` - Anonymous functions
- `Import/ImportFrom` - Module imports

### 3. ExpressionMetrics

Tracks evaluation statistics:

```python
{
    "total_evaluations": 1523,
    "avg_time_ms": 0.42,
    "cache_hit_rate": 23.5,
    "errors": 12,
    "malicious_attempts": 3
}
```

### 4. Exception Types

- `ExpressionSyntaxError` - Invalid expression syntax
- `ExpressionEvaluationError` - Runtime evaluation failures

## Supported Operators

| Operator | Syntax | Example |
|----------|--------|---------|
| Equals | `==` | `status == 'active'` |
| Not equals | `!=` | `status != 'closed'` |
| Greater than | `>` | `priority > 5` |
| Less than | `<` | `count < 10` |
| Greater or equal | `>=` | `priority >= 3` |
| Less or equal | `<=` | `count <= 100` |
| Contains | `in` | `'hello' in message` |
| In list | `in [...]` | `status in ['open', 'pending']` |
| Not in | `not in [...]` | `role not in ['guest']` |
| And | `and` | `a > 0 and b > 0` |
| Or | `or` | `a or b` |
| Not | `not` | `not active` |

## Security Measures

### 1. Pre-parse Pattern Detection

Before parsing, the evaluator checks for known malicious patterns:

```python
MALICIOUS_PATTERNS = [
    r"__import__",
    r"__builtins__",
    r"eval\s*\(",
    r"exec\s*\(",
    r"lambda\s*:",
    r"\.\w+\s*\(",
]
```

### 2. AST Validation

After parsing, the AST is traversed to ensure no dangerous node types are present:

```python
dangerous_nodes = {
    ast.Call,       # Function calls
    ast.Attribute,  # obj.attr
    ast.Lambda,     # lambda expressions
    ast.Import,     # import statements
}
```

### 3. Context Isolation

Variables are only looked up from the provided context dictionary - no access to Python globals or builtins.

## Workflow Integration

The evaluator is integrated into `WorkflowTraversalEngine`:

```python
class WorkflowTraversalEngine:
    def __init__(self, db: AsyncSession):
        self._expression_evaluator = ExpressionEvaluator()

    def _evaluate_expression(self, expression: str, context: dict) -> bool:
        try:
            return self._expression_evaluator.evaluate(expression, context)
        except ExpressionSyntaxError:
            logger.warning(f"Expression syntax error: {e}")
            return False
        except ExpressionEvaluationError:
            logger.warning(f"Expression evaluation error: {e}")
            return False
```

## Metrics Collection

Metrics are automatically collected and can be accessed via:

```python
from app.services.expression_evaluator import get_metrics

metrics = get_metrics()
print(metrics.get_stats())
```

## Testing

Comprehensive tests cover:

- **Basic operators**: equals, not_equals, greater_than, less_than, contains, in_list
- **Logical operators**: and, or, not, complex combinations
- **Malicious payloads**: __import__, eval, exec, lambda, attribute access
- **Invalid syntax**: unbalanced parentheses, unknown operators, undefined variables
- **Performance**: 1000+ evaluations per second
- **Edge cases**: None values, empty strings, zero, floats

## Migration from eval()

**Before (unsafe):**
```python
def _evaluate_expression(self, expression, context):
    for key, value in context.items():
        expression = re.sub(rf"\b{key}\b", f'"{value}"', expression)
    result = eval(expression, {"__builtins__": allowed_names}, {})
    return bool(result)
```

**After (safe):**
```python
def _evaluate_expression(self, expression, context):
    return self._expression_evaluator.evaluate(expression, context)
```

## Performance Characteristics

- Simple expressions: ~0.1ms per evaluation
- Complex expressions (5+ operators): ~0.5ms per evaluation
- Memory footprint: Minimal (no eval globals overhead)

## Future Enhancements

1. **Caching**: Add LRU cache for repeated expression+context combinations
2. **Prepared Statements**: Pre-compile frequently used expressions
3. **Type Inference**: Optimize based on context value types
4. **Custom Functions**: Allow safe registered functions (e.g., `len()`, `upper()`)
/**
 * Segment Transformer
 *
 * Converts frontend SegmentNode structure to backend DSL format.
 *
 * Frontend format (SegmentNode):
 * {
 *   id: string,
 *   op: "and" | "or",
 *   children: (SegmentGroup | SegmentCondition)[]
 * }
 *
 * Backend format (SegmentDefinition):
 * {
 *   op: "and" | "or",
 *   children: (SegmentDefinition | SegmentConditionDef)[]
 * }
 *
 * Note: Backend doesn't support "activity" filter - these conditions are filtered out.
 */

import type { SegmentNode, SegmentGroup, SegmentCondition } from "@/components/contacts/segment-builder";
import {
    type SegmentDslCondition,
    type SegmentDslNode,
    validateSegmentDsl,
} from "@/lib/types/segment-dsl";

type BackendDefinition = SegmentDslCondition & {
    op: string;
    children?: BackendDefinition[];
    child?: BackendDefinition;
};

function isGroup(node: SegmentNode | SegmentGroup): node is SegmentGroup {
    return "op" in node && "children" in node;
}

/**
 * Check if a condition uses the "activity" filter which isn't supported by backend
 */
function hasActivityFilter(node: SegmentNode): boolean {
    if (!isGroup(node)) return false;

    for (const child of node.children) {
        if (isGroup(child)) {
            if (hasActivityFilter(child)) return true;
        } else if (child.op === "activity") {
            return true;
        }
    }
    return false;
}

/**
 * Convert frontend SegmentCondition to backend format
 */
function conditionToBackend(condition: SegmentCondition): BackendCondition {
    const cond: BackendCondition = {
        op: condition.op,
    };

    if (condition.field) cond.field = condition.field;
    if (condition.value !== undefined) cond.value = condition.value;
    if (condition.values) cond.values = condition.values;
    if (condition.tag) cond.tag = condition.tag;
    if (condition.key) cond.key = condition.key;
    if (condition.cmp) cond.cmp = condition.cmp;

    return cond;
}

/**
 * Recursively convert frontend node to backend format
 */
function nodeToBackend(node: SegmentNode): BackendDefinition {
    if (!isGroup(node)) {
        // It's a condition without a group wrapper
        return conditionToBackend(node);
    }

    const result: BackendDefinition = {
        op: node.op,
        children: [],
    };

    for (const child of node.children) {
        if (isGroup(child)) {
            result.children!.push(nodeToBackend(child));
        } else {
            // Skip activity filters - not supported by backend
            if (child.op === "activity") {
                console.warn("Activity filter is not supported by backend, skipping");
                continue;
            }
            result.children!.push(conditionToBackend(child));
        }
    }

    // If children array is empty after filtering, add a dummy condition that matches nothing
    // This ensures the query doesn't fail
    if (result.children!.length === 0) {
        result.children!.push({
            op: "eq",
            field: "name",
            value: "__NO_MATCH__",
        });
    }

    return result;
}

/**
 * Transform frontend SegmentNode to backend DSL format
 * @returns Backend-compatible definition or null if invalid
 */
export function transformSegmentToBackend(segment: SegmentNode): BackendDefinition | null {
    if (!segment) return null;

    // If root is not a group, wrap it
    if (!isGroup(segment)) return conditionToBackend(segment);

    // Check for activity filters
    if (hasActivityFilter(segment)) {
        console.warn("Segment contains activity filters which are not supported by backend");
    }

    const normalized = nodeToBackend(segment);
    const validation = validateSegmentDsl(normalized as SegmentDslNode);
    if (!validation.valid) return null;
    return normalized;
}

/**
 * Validate that segment can be sent to backend
 * Returns array of validation errors
 */
export function validateSegmentForBackend(segment: SegmentNode): string[] {
    const errors: string[] = [];

    if (!segment) {
        errors.push("Segment is empty");
        return errors;
    }

    if (!isGroup(segment)) {
        // Single condition - validate it
        if (segment.op === "activity") {
            errors.push("Activity filter is not supported by backend");
        }
        return errors;
    }

    // Recursively check for unsupported filters
    function checkNode(node: SegmentNode, path: string) {
        if (!isGroup(node)) {
            if (node.op === "activity") {
                errors.push(`Activity filter at ${path} is not supported by backend`);
            }
            return;
        }

        node.children.forEach((child, idx) => {
            if (isGroup(child)) {
                checkNode(child, `${path}[${idx}]`);
            } else if (child.op === "activity") {
                errors.push(`Activity filter at ${path}[${idx}] is not supported by backend`);
            }
        });
    }

    checkNode(segment, "root");

    const backend = transformSegmentToBackend(segment);
    if (!backend) {
        errors.push("Segment definition is invalid");
        return errors;
    }

    const dslValidation = validateSegmentDsl(backend as SegmentDslNode);
    errors.push(...dslValidation.errors);
    return errors;
}

/**
 * Parse backend definition back to frontend format (for editing)
 */
export function parseBackendDefinition(definition: unknown): SegmentNode | null {
    if (!definition || typeof definition !== "object") {
        return null;
    }

    const def = migrateLegacyDefinition(definition as Record<string, unknown>) as BackendDefinition;

    // If it's a simple condition (no children), wrap in group
    if (!def.children || def.children.length === 0) {
        return {
            id: generateId(),
            op: "eq",
            field: def.field,
            value: def.value,
        };
    }

    function parseNode(node: BackendDefinition, id: string): SegmentNode {
        if (node.children) {
            return {
                id,
                op: node.op as "and" | "or",
                children: node.children.map((child, idx) => {
                    if (child.children) {
                        return parseNode(child, generateId());
                    }
                    return {
                        id: generateId(),
                        op: child.op as SegmentCondition["op"],
                        field: child.field,
                        value: child.value,
                        values: child.values,
                        tag: child.tag,
                        key: child.key,
                        cmp: child.cmp,
                    };
                }),
            };
        }

        // It's a condition
        return {
            id,
            op: (node.op || "eq") as SegmentCondition["op"],
            field: node.field,
            value: node.value,
            values: node.values,
            tag: node.tag,
            key: node.key,
            cmp: node.cmp,
        };
    }

    return parseNode(def, generateId());
}

export function migrateLegacyDefinition(definition: Record<string, unknown>): Record<string, unknown> {
    if (!definition || typeof definition !== "object") return definition;

    // Legacy wrapper: { operator, conditions }
    if ("operator" in definition && "conditions" in definition) {
        const operator = String(definition.operator || "").toLowerCase();
        const conditions = Array.isArray(definition.conditions) ? definition.conditions : [];
        return {
            op: operator,
            children: conditions.map((c) => migrateLegacyDefinition((c || {}) as Record<string, unknown>)),
        };
    }

    // Already canonical group
    if (definition.op === "and" || definition.op === "or") {
        const children = Array.isArray(definition.children) ? definition.children : [];
        return {
            ...definition,
            children: children.map((c) => migrateLegacyDefinition((c || {}) as Record<string, unknown>)),
        };
    }

    // Legacy condition style: { field, operator, value }
    if ("field" in definition && "operator" in definition && !("op" in definition)) {
        const operator = String(definition.operator || "").toLowerCase();
        return {
            op: operator === "equals" ? "eq" : operator,
            field: definition.field,
            value: definition.value,
            values: definition.values,
            tag: definition.tag,
            key: definition.key,
            cmp: definition.cmp,
        };
    }

    return definition;
}

function generateId(): string {
    return Math.random().toString(36).substring(2, 11);
}

/**
 * Check if segment has any conditions
 */
export function isSegmentEmpty(segment: SegmentNode): boolean {
    if (!segment) return true;

    if (!isGroup(segment)) {
        // Single condition - check if it has meaningful values
        return !segment.field && !segment.value && !segment.tag && !segment.key;
    }

    if (!segment.children || segment.children.length === 0) {
        return true;
    }

    // Check if all children are empty
    return segment.children.every((child) => {
        if (isGroup(child)) {
            return isSegmentEmpty(child);
        }
        return !child.field && !child.value && !child.tag && !child.key;
    });
}

export type SegmentDslComparisonOp =
    | "eq"
    | "neq"
    | "contains"
    | "in"
    | "gt"
    | "gte"
    | "lt"
    | "lte"
    | "has_tag"
    | "attr";

export type SegmentDslGroupOp = "and" | "or" | "not";

export type SegmentDslNode = SegmentDslGroup | SegmentDslCondition;

export interface SegmentDslGroup {
    op: SegmentDslGroupOp;
    children?: SegmentDslNode[];
    child?: SegmentDslNode;
}

export interface SegmentDslCondition {
    op: SegmentDslComparisonOp;
    field?: "name" | "phone" | "created_at";
    value?: string | number | boolean | null;
    values?: Array<string | number | boolean | null>;
    tag?: string;
    key?: string;
    cmp?: "eq" | "neq" | "contains" | "gt" | "gte" | "lt" | "lte";
}

export interface SegmentDslValidationResult {
    valid: boolean;
    errors: string[];
}

export function validateSegmentDsl(node: unknown): SegmentDslValidationResult {
    const errors: string[] = [];

    const walk = (current: unknown, path: string) => {
        if (!current || typeof current !== "object") {
            errors.push(`${path}: node must be an object`);
            return;
        }
        const n = current as Record<string, unknown>;
        const op = n.op;
        if (typeof op !== "string") {
            errors.push(`${path}: missing op`);
            return;
        }

        if (op === "and" || op === "or") {
            if (!Array.isArray(n.children) || n.children.length === 0) {
                errors.push(`${path}: ${op} requires non-empty children`);
                return;
            }
            n.children.forEach((child, idx) => walk(child, `${path}.children[${idx}]`));
            return;
        }

        if (op === "not") {
            if (!n.child) {
                errors.push(`${path}: not requires child`);
                return;
            }
            walk(n.child, `${path}.child`);
            return;
        }

        if (op === "has_tag") {
            if (typeof n.tag !== "string" || !n.tag.trim()) {
                errors.push(`${path}: has_tag requires non-empty tag`);
            }
            return;
        }

        if (op === "attr") {
            if (typeof n.key !== "string" || !n.key.trim()) {
                errors.push(`${path}: attr requires key`);
            }
            if (typeof n.cmp !== "string") {
                errors.push(`${path}: attr requires cmp`);
            }
            if (!("value" in n)) {
                errors.push(`${path}: attr requires value`);
            }
            return;
        }

        if (["eq", "neq", "contains", "gt", "gte", "lt", "lte"].includes(op)) {
            if (typeof n.field !== "string") {
                errors.push(`${path}: ${op} requires field`);
            }
            if (!("value" in n)) {
                errors.push(`${path}: ${op} requires value`);
            }
            return;
        }

        if (op === "in") {
            if (typeof n.field !== "string") {
                errors.push(`${path}: in requires field`);
            }
            if (!Array.isArray(n.values) || n.values.length === 0) {
                errors.push(`${path}: in requires non-empty values`);
            }
            return;
        }

        errors.push(`${path}: unsupported op ${op}`);
    };

    walk(node, "root");

    return {
        valid: errors.length === 0,
        errors,
    };
}

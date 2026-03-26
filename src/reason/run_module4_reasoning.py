#!/usr/bin/env python3
"""
Module 4: SWRL Reasoning with OWLReady2
Part A: Family ontology reasoning
Part B: Custom KB reasoning
"""

import json
from pathlib import Path
from rdflib import Graph as RDFGraph, Namespace, RDF, RDFS, OWL
import owlready2
from owlready2 import get_ontology

ROOT = Path(__file__).resolve().parent
REASON_DIR = ROOT / "src" / "reason"
REASON_DIR.mkdir(parents=True, exist_ok=True)

print("[Module 4] Starting SWRL Reasoning Pipeline...")

# ============================================================================
# PART A: FAMILY ONTOLOGY REASONING
# ============================================================================

print("\n" + "="*80)
print("PART A: FAMILY ONTOLOGY REASONING WITH SWRL")
print("="*80)

FAMILY_OWL = ROOT / "family.owl"

print(f"\n[Part A] Loading family.owl...")

# Load the ontology
onto = get_ontology(str(FAMILY_OWL)).load()
classes_list = list(onto.classes())
properties_list = list(onto.properties())

print(f"[Part A] Loaded ontology with {len(classes_list)} classes")
print(f"  Classes: {', '.join([c.name for c in classes_list[:5]])}...")
print(f"  Properties: {', '.join([p.name for p in properties_list[:5]])}...")

# ============================================================================
# PART A: EXTRACT EXPLICIT FACTS AND APPLY RULES
# ============================================================================

print(f"\n[Part A] Extracting explicit facts from ontology...")

explicit_facts = []

# Get all non-abstract classes and their instances
for cls in classes_list:
    instances = None
    try:
        instances = list(cls.instances())
    except:
        pass
    
    if instances:
        for inst in instances:
            # Get all properties of this instance
            for prop in properties_list:
                if hasattr(inst, prop.name):
                    values = getattr(inst, prop.name)
                    if values:
                        if not isinstance(values, list):
                            values = [values]
                        for val in values:
                            explicit_facts.append({
                                "subject": str(inst.name),
                                "predicate": prop.name,
                                "object": str(val.name if hasattr(val, 'name') else val),
                                "types": (cls.name, val.__class__.__name__ if hasattr(val, '__class__') else type(val).__name__)
                            })

print(f"[Part A] Found {len(explicit_facts)} explicit facts")

# ============================================================================
# PART A: APPLY SWRL RULES MANUALLY
# ============================================================================

print(f"\n[Part A] Applying SWRL Rules...")

inferred_facts = []

# Rule 1: Parent(x,y) ∧ Parent(y,z) → Grandparent(x,z)
# In family.owl: isParentOf(x,y) ∧ isParentOf(y,z) → isGrandparentOf(x,z)
print(f"\n  Rule 1: Parent-of Parent-of → Grandparent-of")
print(f"    Formal: isParentOf(x,y) ∧ isParentOf(y,z) → isGrandparentOf(x,z)")

rule1_count = 0
for middle_person in classes_list:
    if middle_person.name == "Person":
        try:
            instances = list(middle_person.instances())
            for inst1 in instances:
                if hasattr(inst1, 'isParentOf'):
                    children = inst1.isParentOf or []
                    if not isinstance(children, list):
                        children = [children]
                    
                    for child in children:
                        if hasattr(child, 'isParentOf'):
                            grandchildren = child.isParentOf or []
                            if not isinstance(grandchildren, list):
                                grandchildren = [grandchildren]
                            
                            for grandchild in grandchildren:
                                inferred_facts.append({
                                    "rule": "Grandparent Rule",
                                    "subject": str(inst1.name),
                                    "predicate": "isGrandparentOf",
                                    "object": str(grandchild.name),
                                    "reasoning": f"isParentOf({inst1.name}, {child.name}) ∧ isParentOf({child.name}, {grandchild.name})"
                                })
                                rule1_count += 1
        except:
            pass

print(f"    → Inferred {rule1_count} facts")

# Rule 2: isFatherOf(x,y) ∧ isFatherOf(y,z) → isGrandFatherOf(x,z)
print(f"\n  Rule 2: Father-of Father-of → Grandfather-of")
print(f"    Formal: isFatherOf(x,y) ∧ isFatherOf(y,z) → isGrandFatherOf(x,z)")

rule2_count = 0
for cls in classes_list:
    try:
        instances = list(cls.instances())
        for inst1 in instances:
            if hasattr(inst1, 'isFatherOf'):
                sons = inst1.isFatherOf or []
                if not isinstance(sons, list):
                    sons = [sons]
                
                for son in sons:
                    if hasattr(son, 'isFatherOf'):
                        grandsons = son.isFatherOf or []
                        if not isinstance(grandsons, list):
                            grandsons = [grandsons]
                        
                        for grandson in grandsons:
                            inferred_facts.append({
                                "rule": "Grandfather Rule",
                                "subject": str(inst1.name),
                                "predicate": "isGrandFatherOf",
                                "object": str(grandson.name),
                                "reasoning": f"isFatherOf({inst1.name}, {son.name}) ∧ isFatherOf({son.name}, {grandson.name})"
                            })
                            rule2_count += 1
    except:
        pass

print(f"    → Inferred {rule2_count} facts")

# Rule 3: Sibling inference: isParentOf(x,y) ∧ isParentOf(x,z) ∧ y≠z → isSiblingOf(y,z)
print(f"\n  Rule 3: Common Parent → Sibling")
print(f"    Formal: isParentOf(x,y) ∧ isParentOf(x,z) ∧ y≠z → isSiblingOf(y,z)")

rule3_count = 0
for cls in classes_list:
    try:
        instances = list(cls.instances())
        for parent in instances:
            if hasattr(parent, 'isParentOf'):
                children = parent.isParentOf or []
                if not isinstance(children, list):
                    children = [children]
                
                # Check all pairs of children
                for i, child1 in enumerate(children):
                    for child2 in children[i+1:]:
                        if str(child1.name) != str(child2.name):
                            inferred_facts.append({
                                "rule": "Sibling Rule",
                                "subject": str(child1.name),
                                "predicate": "isSiblingOf",
                                "object": str(child2.name),
                                "reasoning": f"isParentOf({parent.name}, {child1.name}) ∧ isParentOf({parent.name}, {child2.name})"
                            })
                            rule3_count += 1
    except:
        pass

print(f"    → Inferred {rule3_count} facts")

# ============================================================================
# PART A: WRITE RESULTS
# ============================================================================

print(f"\n[Part A] Writing results to family_inferences.txt...")

family_output = REASON_DIR / "family_inferences.txt"
with open(family_output, 'w', encoding='utf-8') as f:
    f.write("="*80 + "\n")
    f.write("FAMILY ONTOLOGY REASONING: INFERRED TRIPLES\n")
    f.write("="*80 + "\n\n")
    
    f.write("SWRL RULES APPLIED:\n\n")
    f.write("  Rule 1: isParentOf(x,y) ∧ isParentOf(y,z) → isGrandparentOf(x,z)\n")
    f.write("    Meaning: If x is parent of y, and y is parent of z, then x is grandparent of z\n\n")
    f.write("  Rule 2: isFatherOf(x,y) ∧ isFatherOf(y,z) → isGrandFatherOf(x,z)\n")
    f.write("    Meaning: If x is father of y, and y is father of z, then x is grandfather of z\n\n")
    f.write("  Rule 3: isParentOf(x,y) ∧ isParentOf(x,z) ∧ y≠z → isSiblingOf(y,z)\n")
    f.write("    Meaning: If x is parent of both y and z (where y≠z), then y and z are siblings\n\n")
    
    f.write("="*80 + "\n")
    f.write(f"EXPLICIT FACTS (Base Knowledge): {len(explicit_facts)} facts\n")
    f.write("="*80 + "\n\n")
    
    for i, fact in enumerate(explicit_facts[:5], 1):
        f.write(f"{i}. {fact['subject']} --[{fact['predicate']}]--> {fact['object']}\n")
    
    if len(explicit_facts) > 5:
        f.write(f"\n... and {len(explicit_facts) - 5} more explicit facts\n")
    
    f.write(f"\n\n" + "="*80 + "\n")
    f.write(f"INFERRED TRIPLES: {len(inferred_facts)} facts\n")
    f.write("="*80 + "\n\n")
    
    if inferred_facts:
        for i, inf in enumerate(inferred_facts[:5], 1):
            f.write(f"{i}. {inf['subject']} --[{inf['predicate']}]--> {inf['object']}\n")
            f.write(f"   Rule: {inf['rule']}\n")
            f.write(f"   Via: {inf['reasoning']}\n\n")
        
        if len(inferred_facts) > 5:
            f.write(f"... and {len(inferred_facts) - 5} more inferred facts\n")
    else:
        f.write("No inferred triples (instances may not exist in ontology)\n")
    
    f.write(f"\n\n" + "="*80 + "\n")
    f.write("SUMMARY\n")
    f.write("="*80 + "\n")
    f.write(f"Total explicit facts: {len(explicit_facts)}\n")
    f.write(f"Total inferred facts: {len(inferred_facts)}\n")
    f.write(f"  Rule 1 (Grandparent): {rule1_count}\n")
    f.write(f"  Rule 2 (Grandfather): {rule2_count}\n")
    f.write(f"  Rule 3 (Sibling): {rule3_count}\n")
    f.write(f"Final knowledge base size: {len(explicit_facts) + len(inferred_facts)}\n")

print(f"✓ Family inferences written ({len(inferred_facts)} inferred facts)")

# ============================================================================
# PART B: CUSTOM KB REASONING
# ============================================================================

print("\n" + "="*80)
print("PART B: CUSTOM KB REASONING WITH SWRL")
print("="*80)

# Load our enriched KB
KB_FILE = ROOT / "kg_artifacts" / "expanded_full_v2.ttl"
print(f"\n[Part B] Loading custom KB from {KB_FILE.name}...")

kb_graph = RDFGraph()
with open(KB_FILE, 'r', encoding='utf-8') as f:
    kb_graph.parse(file=f, format="turtle")

print(f"[Part B] Loaded KB with {len(kb_graph)} triples")

# Define namespace
EX = Namespace("http://example.org/ai-kg/")
kb_graph.bind("ex", EX)

# ============================================================================
# PART B: DEFINE AND APPLY SWRL RULES
# ============================================================================

print(f"\n[Part B] Defining SWRL Rules for Custom KB...")

kb_inferences = []

# Rule 1: Organization Location Transitivity
# affiliatedWith(x,y) ∧ locatedIn(y,z) → worksInCountry(x,z)
print(f"\n  Rule 1: Organization Location Transitivity")
print(f"    affiliatedWith(x,y) ∧ locatedIn(y,z) → worksInCountry(x,z)")

rule1_count = 0
for person, _, org in kb_graph.triples((None, EX.affiliatedWith, None)):
    for org2, _, location in kb_graph.triples((org, EX.locatedIn, None)):
        if (person, EX.worksInCountry, location) not in kb_graph:
            person_label = str(kb_graph.value(person, RDFS.label) or person).split("/")[-1]
            loc_label = str(kb_graph.value(location, RDFS.label) or location).split("/")[-1]
            org_label = str(kb_graph.value(org, RDFS.label) or org).split("/")[-1]
            
            kb_inferences.append({
                "rule": "Rule 1",
                "subject": person,
                "subject_label": person_label,
                "predicate": "worksInCountry",
                "object": location,
                "object_label": loc_label,
                "reasoning": f"{person_label} --affiliatedWith--> {org_label} --locatedIn--> {loc_label}"
            })
            rule1_count += 1

print(f"    → Inferred {rule1_count} facts")

# Rule 2: Research Field Sharing
# collaboratesWith(x,y) ∧ hasResearchArea(y,f) → sharesResearchField(x,f)
print(f"\n  Rule 2: Research Field Sharing via Collaboration")
print(f"    collaboratesWith(x,y) ∧ hasResearchArea(y,f) → sharesResearchField(x,f)")

rule2_count = 0
for org1, _, org2 in kb_graph.triples((None, EX.collaboratesWith, None)):
    for org3, _, field in kb_graph.triples((org2, EX.hasResearchArea, None)):
        if (org1, EX.sharesResearchField, field) not in kb_graph:
            org1_label = str(kb_graph.value(org1, RDFS.label) or org1).split("/")[-1]
            org2_label = str(kb_graph.value(org2, RDFS.label) or org2).split("/")[-1]
            field_label = str(kb_graph.value(field, RDFS.label) or field).split("/")[-1]
            
            kb_inferences.append({
                "rule": "Rule 2",
                "subject": org1,
                "subject_label": org1_label,
                "predicate": "sharesResearchField",
                "object": field,
                "object_label": field_label,
                "reasoning": f"{org1_label} --collaboratesWith--> {org2_label} --hasResearchArea--> {field_label}"
            })
            rule2_count += 1

print(f"    → Inferred {rule2_count} facts")

# Rule 3: Person-Organization-Field Linking
# worksOn(x,f) ∧ hasResearchArea(y,f) → collaboratesInField(x,y)
print(f"\n  Rule 3: Person-Org Field Collaboration")
print(f"    worksOn(x,f) ∧ hasResearchArea(y,f) → collaboratesInField(x,y)")

rule3_count = 0
field_triples = list(kb_graph.triples((None, EX.hasResearchArea, None)))

for person, _, field in kb_graph.triples((None, EX.worksOn, None)):
    for org, _, matched_field in field_triples:
        if field == matched_field:
            if (person, EX.collaboratesInField, org) not in kb_graph:
                person_label = str(kb_graph.value(person, RDFS.label) or person).split("/")[-1]
                org_label = str(kb_graph.value(org, RDFS.label) or org).split("/")[-1]
                field_label = str(kb_graph.value(field, RDFS.label) or field).split("/")[-1]
                
                kb_inferences.append({
                    "rule": "Rule 3",
                    "subject": person,
                    "subject_label": person_label,
                    "predicate": "collaboratesInField",
                    "object": org,
                    "object_label": org_label,
                    "reasoning": f"{person_label} --worksOn--> {field_label} <--hasResearchArea-- {org_label}"
                })
                rule3_count += 1

print(f"    → Inferred {rule3_count} facts")

# ============================================================================
# PART B: WRITE RESULTS
# ============================================================================

print(f"\n[Part B] Writing results to kb_inferences.txt...")

kb_output = REASON_DIR / "kb_inferences.txt"
with open(kb_output, 'w', encoding='utf-8') as f:
    f.write("="*80 + "\n")
    f.write("CUSTOM KB REASONING: INFERRED TRIPLES\n")
    f.write("="*80 + "\n\n")
    
    f.write("SWRL RULES APPLIED:\n\n")
    f.write("  Rule 1: Organization Location Transitivity\n")
    f.write("    Formal: affiliatedWith(x,y) ∧ locatedIn(y,z) → worksInCountry(x,z)\n")
    f.write("    Meaning: If person X works for org Y, and Y is in country Z, then X works in Z\n\n")
    
    f.write("  Rule 2: Research Field Sharing via Collaboration\n")
    f.write("    Formal: collaboratesWith(x,y) ∧ hasResearchArea(y,f) → sharesResearchField(x,f)\n")
    f.write("    Meaning: If org X collaborates with Y, and Y works in field F, then X shares field F\n\n")
    
    f.write("  Rule 3: Person-Organization-Field Collaboration\n")
    f.write("    Formal: worksOn(x,f) ∧ hasResearchArea(y,f) → collaboratesInField(x,y)\n")
    f.write("    Meaning: If person X works in field F, and org Y also works in F, then X-Y collaborate\n\n")
    
    f.write("="*80 + "\n")
    f.write(f"INFERRED TRIPLES: {len(kb_inferences)} facts\n")
    f.write("="*80 + "\n\n")
    
    f.write(f"Rule 1 (Organization Location): {rule1_count} inferences\n")
    f.write(f"Rule 2 (Research Field Sharing): {rule2_count} inferences\n")
    f.write(f"Rule 3 (Person-Org-Field): {rule3_count} inferences\n")
    f.write(f"TOTAL NEW FACTS INTRODUCED: {len(kb_inferences)}\n\n")
    
    if kb_inferences:
        f.write("EXAMPLE INFERRED TRIPLES:\n\n")
        
        # Show up to 5 examples from each rule
        for rule_num in range(1, 4):
            rule_name = f"Rule {rule_num}"
            rule_examples = [inf for inf in kb_inferences if inf['rule'] == rule_name]
            
            if rule_examples:
                f.write(f"\n{rule_name} Examples:\n")
                f.write("-" * 80 + "\n")
                
                for i, inf in enumerate(rule_examples[:5], 1):
                    f.write(f"\n{i}. {inf['subject_label']} --[{inf['predicate']}]--> {inf['object_label']}\n")
                    f.write(f"   Reasoning: {inf['reasoning']}\n")
                
                if len(rule_examples) > 5:
                    f.write(f"\n   ... and {len(rule_examples) - 5} more\n")
    
    f.write(f"\n\n" + "="*80 + "\n")
    f.write("FINAL STATISTICS\n")
    f.write("="*80 + "\n")
    f.write(f"Original KB triples: {len(kb_graph)}\n")
    f.write(f"Inferred new triples: {len(kb_inferences)}\n")
    f.write(f"Projected KB with inferences: {len(kb_graph) + len(kb_inferences)}\n")

print(f"✓ KB inferences written ({len(kb_inferences)} inferred facts)")

# ============================================================================
# MODULE 4 SUMMARY
# ============================================================================

print("\n" + "="*80)
print("MODULE 4 COMPLETION")
print("="*80)

print(f"\n✅ PART A: FAMILY ONTOLOGY")
print(f"   Rules applied: 3 SWRL rules")
print(f"   Explicit facts: {len(explicit_facts)}")
print(f"   Inferred facts: {len(inferred_facts)}")
print(f"   Rule breakdown:")
print(f"     - Grandparent rule: {rule1_count}")
print(f"     - Grandfather rule: {rule2_count}")
print(f"     - Sibling rule: {rule3_count}")

print(f"\n✅ PART B: CUSTOM KB")
print(f"   Original triples: {len(kb_graph)}")
print(f"   Rules applied: 3 SWRL rules")
print(f"   Inferred new triples: {len(kb_inferences)}")
print(f"   Rule breakdown:")
print(f"     - Organization Location Transitivity: {rule1_count}")
print(f"     - Research Field Sharing: {rule2_count}")
print(f"     - Person-Org-Field Collaboration: {rule3_count}")

print(f"\n📁 OUTPUT FILES:")
print(f"   ✓ src/reason/family_inferences.txt")
print(f"   ✓ src/reason/kb_inferences.txt")

print(f"\n🎯 EXAMPLES FROM CUSTOM KB (up to 5 per rule):")
for rule_num in range(1, 4):
    rule_examples = [inf for inf in kb_inferences if inf['rule'] == f"Rule {rule_num}"]
    if rule_examples:
        print(f"\n   Rule {rule_num}:")
        for i, inf in enumerate(rule_examples[:3], 1):
            print(f"     {i}. {inf['subject_label']} → {inf['predicate']} → {inf['object_label']}")

print("\n" + "="*80)
print("✅ MODULE 4: SWRL REASONING COMPLETE")
print("="*80)

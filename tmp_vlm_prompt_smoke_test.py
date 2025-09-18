# Quick smoke test for VLM->SD prompt filtering
from backend.models.vlm import VLMAttributes, to_prompt

# Case: placeholder/abstract category and gray colors
attrs1 = VLMAttributes(category='abstract', colors=['gray'], size='medium', orientation='front', details=[''])
print('attrs1 prompt:', to_prompt(attrs1))

# Case: meaningful category and colors
attrs2 = VLMAttributes(category='vehicle', colors=['blue'], size='large', orientation='front', details=['car'])
print('attrs2 prompt:', to_prompt(attrs2))

# Case: long raw fallback present (should not be included unless substantive)
attrs3 = VLMAttributes(category='object', colors=['gray'], size='medium', orientation='front', details=['This is a long descriptive fallback that mentions a shiny blue sports car with headlights and decals and is suitable for generating an accurate SD prompt because it contains many descriptive tokens.'])
print('attrs3 prompt:', to_prompt(attrs3))

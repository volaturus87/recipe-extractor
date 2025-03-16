from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import re
import json
import os
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-this')

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

def extract_recipe(url):
    try:
        session = requests.Session()
        # First request to get cookies
        session.get('https://www.allrecipes.com')
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.allrecipes.com/',
            'DNT': '1'
        }
        
        # Wait briefly to avoid rate limiting
        time.sleep(1)
        
        # Make the actual request
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        ingredients = []
        instructions = []
        
        # Special handling for Kiku Corner
        if 'kikucorner.com' in url:
            recipe_card = soup.find('div', class_='wprm-recipe-container')
            if recipe_card:
                # Get ingredients
                ingredient_items = recipe_card.find_all('li', class_='wprm-recipe-ingredient')
                for item in ingredient_items:
                    amount = item.find('span', class_='wprm-recipe-ingredient-amount')
                    unit = item.find('span', class_='wprm-recipe-ingredient-unit')
                    name = item.find('span', class_='wprm-recipe-ingredient-name')
                    notes = item.find('span', class_='wprm-recipe-ingredient-notes')
                    
                    ingredient_parts = []
                    if amount and amount.text.strip():
                        ingredient_parts.append(amount.text.strip())
                    if unit and unit.text.strip():
                        ingredient_parts.append(unit.text.strip())
                    if name and name.text.strip():
                        ingredient_parts.append(name.text.strip())
                    if notes and notes.text.strip():
                        ingredient_parts.append(f"({notes.text.strip()})")
                    
                    if ingredient_parts:
                        ingredients.append(' '.join(ingredient_parts))
                
                # Get instructions
                instruction_items = recipe_card.find_all('div', class_='wprm-recipe-instruction-text')
                instructions = [item.text.strip() for item in instruction_items if item.text.strip()]

        # Special handling for AllRecipes
        elif 'allrecipes.com' in url:
            # Method 1: Try finding ingredients by class names (older format)
            ingredient_items = soup.find_all(['span', 'li'], class_=['ingredients-item-name', 'ingredients__list-item'])
            if ingredient_items:
                ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
            
            # Method 2: Try finding ingredients section by heading (newer format)
            if not ingredients:
                content = soup.get_text()
                ingredients_match = re.search(r'Ingredients\s*(.*?)(?=Directions|Instructions|Steps|Nutrition Facts|$)', content, re.DOTALL | re.IGNORECASE)
                if ingredients_match:
                    ingredients_text = ingredients_match.group(1)
                    # Remove the "Original recipe yields" line
                    ingredients_text = re.sub(r'Original recipe.*?yields.*?\n', '', ingredients_text)
                    # Split by newlines and clean up
                    ingredients = []
                    for line in ingredients_text.split('\n'):
                        line = line.strip()
                        # Remove bullet points and dashes
                        line = re.sub(r'^[-•]\s*', '', line)
                        if line and not line.startswith('Advertisement') and len(line) > 1:
                            ingredients.append(line)
                    # Remove duplicates while preserving order
                    ingredients = list(dict.fromkeys(ingredients))
            
            # Get all text content for directions
            content = soup.get_text()
            
            # Find the directions section
            directions_match = re.search(r'Directions\s*(.*?)(?=You might also like|Nutrition Facts|$)', content, re.DOTALL | re.IGNORECASE)
            if directions_match:
                directions_text = directions_match.group(1)
                
                # Split into steps and clean up
                steps = re.split(r'\s*\d+\.\s+', directions_text)
                
                # Process each step
                for step in steps:
                    # Clean up the step text
                    step = step.strip()
                    # Remove image credits and other noise
                    step = re.sub(r'Dotdash Meredith.*?Studios', '', step, flags=re.IGNORECASE)
                    step = re.sub(r'Advertisement', '', step, flags=re.IGNORECASE)
                    step = ' '.join(step.split())  # Normalize whitespace
                    
                    # Only keep meaningful steps
                    if step and len(step) > 10 and not step.startswith('You might also like'):
                        instructions.append(step)
                
                # Remove the first item if it's empty (from the split)
                if instructions and not instructions[0]:
                    instructions.pop(0)

        # Special handling for Food Network
        elif 'foodnetwork.com' in url:
            # Get ingredients
            ingredient_items = soup.find_all('span', class_='o-Ingredients__a-Ingredient')
            ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
            
            # Get instructions
            instruction_section = soup.find('div', class_='o-Method__m-Body')
            if instruction_section:
                instruction_items = instruction_section.find_all(['p', 'li'])
                instructions = [item.text.strip() for item in instruction_items if item.text.strip()]

        # Special handling for Simply Recipes
        elif 'simplyrecipes.com' in url:
            recipe_card = soup.find('div', class_='structured-project-content')
            if recipe_card:
                # Get ingredients
                ingredient_items = recipe_card.find_all('li', class_='structured-ingredients__list-item')
                ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
                
                # Get instructions
                instruction_items = recipe_card.find_all('li', class_='structured-project__step')
                instructions = [item.text.strip() for item in instruction_items if item.text.strip()]

        # Special handling for Epicurious
        elif 'epicurious.com' in url:
            # Get ingredients
            ingredient_items = soup.find_all('div', class_='ingredient')
            ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
            
            # Get instructions
            instruction_items = soup.find_all('li', class_='preparation-step')
            instructions = [item.text.strip() for item in instruction_items if item.text.strip()]

        # Special handling for Serious Eats
        elif 'seriouseats.com' in url:
            recipe_card = soup.find('div', class_='recipe-card')
            if recipe_card:
                # Get ingredients
                ingredient_items = recipe_card.find_all('li', class_='ingredient')
                ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
                
                # Get instructions
                instruction_items = recipe_card.find_all('li', class_='recipe-procedure')
                instructions = [item.text.strip() for item in instruction_items if item.text.strip()]

        # Special handling for House of Nash Eats
        elif 'houseofnasheats.com' in url:
            recipe_card = soup.find('div', class_='tasty-recipes')
            if recipe_card:
                # Get ingredients
                ingredients_section = recipe_card.find('div', class_='tasty-recipes-ingredients')
                if ingredients_section:
                    ingredient_items = ingredients_section.find_all('li')
                    ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
                
                # Get instructions
                instructions_section = recipe_card.find('div', class_='tasty-recipes-instructions')
                if instructions_section:
                    instruction_items = instructions_section.find_all('li')
                    instructions = [item.text.strip() for item in instruction_items if item.text.strip()]

        # Special handling for Just One Cookbook
        elif 'justonecookbook.com' in url:
            recipe_card = soup.find('div', class_='wprm-recipe-container')
            if recipe_card:
                # Get ingredients
                ingredient_items = recipe_card.find_all('li', class_='wprm-recipe-ingredient')
                for item in ingredient_items:
                    amount = item.find('span', class_='wprm-recipe-ingredient-amount')
                    unit = item.find('span', class_='wprm-recipe-ingredient-unit')
                    name = item.find('span', class_='wprm-recipe-ingredient-name')
                    notes = item.find('span', class_='wprm-recipe-ingredient-notes')
                    
                    ingredient_parts = []
                    if amount and amount.text.strip():
                        ingredient_parts.append(amount.text.strip())
                    if unit and unit.text.strip():
                        ingredient_parts.append(unit.text.strip())
                    if name and name.text.strip():
                        ingredient_parts.append(name.text.strip())
                    if notes and notes.text.strip():
                        ingredient_parts.append(f"({notes.text.strip()})")
                    
                    if ingredient_parts:
                        ingredients.append(' '.join(ingredient_parts))
                
                # Get instructions
                instruction_items = recipe_card.find_all('div', class_='wprm-recipe-instruction-text')
                instructions = [item.text.strip() for item in instruction_items if item.text.strip()]
        
        # If specific site handling failed, try generic methods
        if not ingredients and not instructions:
            # Try schema.org Recipe markup
            recipe_schema = soup.find('script', type='application/ld+json')
            if recipe_schema:
                try:
                    data = json.loads(recipe_schema.string)
                    if isinstance(data, dict):
                        if '@graph' in data:
                            for item in data['@graph']:
                                if '@type' in item and item['@type'] == 'Recipe':
                                    data = item
                                    break
                        if 'recipeIngredient' in data:
                            ingredients = data['recipeIngredient']
                        elif 'ingredients' in data:
                            ingredients = data['ingredients']
                        if 'recipeInstructions' in data:
                            if isinstance(data['recipeInstructions'], list):
                                instructions = [step.get('text', step) if isinstance(step, dict) else step 
                                             for step in data['recipeInstructions']]
                            else:
                                instructions = [data['recipeInstructions']]
                except json.JSONDecodeError:
                    print("Failed to parse recipe schema JSON")
            
            # Fallback to common HTML patterns if still no ingredients found
            if not ingredients:
                ingredients_list = soup.find_all(['ul', 'ol'], class_=re.compile('ingredient|ingredients', re.I))
                for ing_list in ingredients_list:
                    ingredients.extend([item.text.strip() for item in ing_list.find_all('li')])
                
                if not ingredients:
                    ingredient_elements = soup.find_all(['p', 'div'], class_=re.compile('ingredient|ingredients', re.I))
                    for element in ingredient_elements:
                        text = element.text.strip()
                        if text and not any(common in text.lower() for common in ['direction', 'instruction', 'method']):
                            ingredients.append(text)
            
            # Fallback to common HTML patterns if still no instructions found
            if not instructions:
                instructions_list = soup.find_all(['ul', 'ol'], class_=re.compile('instruction|direction|step|method', re.I))
                for inst_list in instructions_list:
                    instructions.extend([item.text.strip() for item in inst_list.find_all('li')])
                
                if not instructions:
                    instruction_elements = soup.find_all(['p', 'div'], class_=re.compile('instruction|direction|step|method', re.I))
                    for element in instruction_elements:
                        text = element.text.strip()
                        if text and not any(common in text.lower() for common in ['ingredient']):
                            instructions.append(text)
        
        # Clean up the extracted data
        ingredients = [i.strip() for i in ingredients if i.strip()]
        instructions = [i.strip() for i in instructions if i.strip()]
        
        if not ingredients and not instructions:
            return {'error': 'Could not find recipe content. Please make sure the URL contains a recipe.'}
            
        return {
            'ingredients': ingredients,
            'instructions': instructions
        }
    except requests.RequestException as e:
        return {'error': f'Failed to fetch the webpage: {str(e)}'}
    except Exception as e:
        return {'error': f'An error occurred while extracting the recipe: {str(e)}'}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
def extract():
    url = request.form.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'})
    
    if not url.startswith(('http://', 'https://')):
        return jsonify({'error': 'Please provide a valid URL starting with http:// or https://'})
    
    recipe_data = extract_recipe(url)
    return jsonify(recipe_data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

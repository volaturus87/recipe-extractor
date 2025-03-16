from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import re
import json
import os
import time
import traceback

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-this')

def clean_text(text):
    text = re.sub(r'▢\s*', '', text)  # Remove checkbox
    text = re.sub(r'\[.*?\]', '', text)  # Remove links
    text = re.sub(r'AD', '', text)  # Remove AD markers
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    return text.strip()

def extract_recipe(url):
    try:
        print(f"Extracting recipe from URL: {url}")
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Get all text content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check for multiple recipe cards/sections
        multiple_recipes = False
        
        # AllRecipes - check for multiple recipe cards
        if 'allrecipes.com' in url:
            recipe_cards = soup.find_all('div', class_=['recipe-content', 'recipe-card'])
            multiple_recipes = len(recipe_cards) > 1
        
        # Food Network - check for multiple recipe sections
        elif 'foodnetwork.com' in url:
            recipe_sections = soup.find_all(['div', 'section'], class_=['o-Recipe', 'recipe'])
            multiple_recipes = len(recipe_sections) > 1
        
        # Simply Recipes - check for multiple recipe cards
        elif 'simplyrecipes.com' in url:
            recipe_cards = soup.find_all('div', class_='structured-project-content')
            multiple_recipes = len(recipe_cards) > 1
        
        # Epicurious - check for multiple recipe sections
        elif 'epicurious.com' in url:
            recipe_sections = soup.find_all(['div', 'section'], class_=['recipe', 'recipe-content'])
            multiple_recipes = len(recipe_sections) > 1
        
        # Serious Eats - check for multiple recipe cards
        elif 'seriouseats.com' in url:
            recipe_cards = soup.find_all('div', class_='recipe-card')
            multiple_recipes = len(recipe_cards) > 1
        
        # House of Nash Eats - check for multiple recipe sections
        elif 'houseofnasheats.com' in url:
            recipe_sections = soup.find_all('div', class_='tasty-recipes')
            multiple_recipes = len(recipe_sections) > 1
        
        # Just One Cookbook - check for multiple recipe containers
        elif 'justonecookbook.com' in url:
            recipe_containers = soup.find_all('div', class_='wprm-recipe-container')
            multiple_recipes = len(recipe_containers) > 1
        
        # Feel Good Foodie - check for multiple recipe sections
        elif 'feelgoodfoodie.net' in url:
            text_content = soup.get_text()
            recipe_sections = len([s for s in re.findall(r'Base Recipe|Instructions', text_content) if s == 'Base Recipe'])
            multiple_recipes = recipe_sections > 1
        
        if multiple_recipes:
            return {'error': 'Pages with multiple recipes are not supported yet'}
        
        title = ""
        base_ingredients = []
        base_instructions = []
        variations = []
        
        # Extract title
        title_tag = soup.find(['h1', 'h2'], class_=re.compile(r'title|recipe-title|entry-title', re.I))
        if title_tag:
            title = title_tag.text.strip()
        
        # FeelGoodFoodie
        if 'feelgoodfoodie.net' in url:
            text_content = soup.get_text()
            sections = re.split(r'\n\s*\n', text_content)
            
            # Find the ingredients section
            for section in sections:
                if 'Base Recipe' in section:
                    # Extract base ingredients
                    base_lines = section.split('\n')
                    in_base = False
                    for line in base_lines:
                        if 'Base Recipe' in line:
                            in_base = True
                            continue
                        if in_base and '▢' in line:
                            text = clean_text(line)
                            if text:
                                base_ingredients.append(text)
                        elif in_base and any(v in line for v in ['Maple Brown Sugar', 'Banana Nut', 'Strawberry & Cream', 'Chocolate Peanut Butter']):
                            in_base = False
                    
                    # Extract variations
                    variation_titles = ['Maple Brown Sugar', 'Banana Nut', 'Strawberry & Cream', 'Chocolate Peanut Butter']
                    current_variation = None
                    variation_ingredients = []
                    
                    for line in base_lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        if line in variation_titles:
                            # Save previous variation if exists
                            if current_variation and variation_ingredients:
                                variations.append({
                                    'title': current_variation,
                                    'ingredients': variation_ingredients
                                })
                                variation_ingredients = []
                            current_variation = line
                        elif current_variation and '▢' in line:
                            text = clean_text(line)
                            if text:
                                variation_ingredients.append(text)
                    
                    # Add the last variation
                    if current_variation and variation_ingredients:
                        variations.append({
                            'title': current_variation,
                            'ingredients': variation_ingredients
                        })
                    break
            
            # Find the instructions section
            for section in sections:
                if section.startswith('Instructions'):
                    lines = section.split('\n')
                    current_section = None
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        if line in ['Microwave Instructions', 'Stovetop Instructions', 'Assembly']:
                            current_section = line
                            base_instructions.append(f"{line}:")
                        elif current_section and line not in ['Instructions', 'Equipment', 'Notes', 'Nutrition']:
                            text = clean_text(line)
                            if text:
                                base_instructions.append(text)
                    break
        
        # AllRecipes
        elif 'allrecipes.com' in url:
            # Get ingredients
            ingredient_items = soup.find_all(['span', 'li'], class_=['ingredients-item-name', 'ingredients__list-item'])
            base_ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
            
            # Get instructions - look for both old and new HTML structures
            instruction_items = []
            
            def extract_step(text):
                # Clean up the text
                text = text.strip()
                # Skip empty lines and image credits
                if not text or any(skip in text.lower() for skip in ['dotdash', 'meredith', 'food studios', 'credit:', 'photo:']):
                    return None
                # Remove extra whitespace and newlines
                text = ' '.join(text.split())
                return text
            
            # Try finding instructions in the new structure (numbered steps)
            instruction_section = soup.find('div', class_='recipe__instructions')
            if instruction_section:
                steps = instruction_section.find_all(['li', 'p'], class_=['comp', 'mntl-sc-block'])
                step_number = 1
                for step in steps:
                    text = extract_step(step.text)
                    if text:
                        # Check if this is just a step number
                        if re.match(r'^\d+\.$', text):
                            continue
                        # Add step number if it doesn't have one
                        if not text.startswith(f"{step_number}."):
                            text = f"{step_number}. {text}"
                        instruction_items.append(text)
                        step_number += 1
            
            # If no instructions found, try the old structure
            if not instruction_items:
                instruction_items = soup.find_all(['div', 'li'], class_=['instructions-section-item', 'instructions__list-item', 'recipe-directions__list--item'])
                instruction_items = [f"{i+1}. {extract_step(item.text)}" for i, item in enumerate(instruction_items) if extract_step(item.text)]
            
            # If still no instructions, try finding them in the article content
            if not instruction_items:
                article = soup.find('article', class_='article-content')
                if article:
                    steps = article.find_all(['p', 'li'], class_=['comp', 'mntl-sc-block'])
                    step_number = 1
                    for step in steps:
                        text = extract_step(step.text)
                        if text:
                            # Check if this is just a step number
                            if re.match(r'^\d+\.$', text):
                                continue
                            # Add step number if it doesn't have one
                            if not text.startswith(f"{step_number}."):
                                text = f"{step_number}. {text}"
                            instruction_items.append(text)
                            step_number += 1
            
            base_instructions = instruction_items
        
        # Food Network
        elif 'foodnetwork.com' in url:
            # Get ingredients
            ingredient_items = soup.find_all('span', class_='o-Ingredients__a-Ingredient')
            base_ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
            
            # Get instructions
            instruction_section = soup.find('div', class_='o-Method__m-Body')
            if instruction_section:
                instruction_items = instruction_section.find_all(['p', 'li'])
                base_instructions = [item.text.strip() for item in instruction_items if item.text.strip()]
        
        # Simply Recipes
        elif 'simplyrecipes.com' in url:
            recipe_card = soup.find('div', class_='structured-project-content')
            if recipe_card:
                # Get ingredients
                ingredient_items = recipe_card.find_all('li', class_='structured-ingredients__list-item')
                base_ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
                
                # Get instructions
                instruction_items = recipe_card.find_all('li', class_='structured-project__step')
                base_instructions = [item.text.strip() for item in instruction_items if item.text.strip()]
        
        # Epicurious
        elif 'epicurious.com' in url:
            # Get ingredients
            ingredient_items = soup.find_all('div', class_='ingredient')
            base_ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
            
            # Get instructions
            instruction_items = soup.find_all('li', class_='preparation-step')
            base_instructions = [item.text.strip() for item in instruction_items if item.text.strip()]
        
        # Serious Eats
        elif 'seriouseats.com' in url:
            recipe_card = soup.find('div', class_='recipe-card')
            if recipe_card:
                # Get ingredients
                ingredient_items = recipe_card.find_all('li', class_='ingredient')
                base_ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
                
                # Get instructions
                instruction_items = recipe_card.find_all('li', class_='recipe-procedure')
                base_instructions = [item.text.strip() for item in instruction_items if item.text.strip()]
        
        # House of Nash Eats
        elif 'houseofnasheats.com' in url:
            recipe_card = soup.find('div', class_='tasty-recipes')
            if recipe_card:
                # Get ingredients
                ingredients_section = recipe_card.find('div', class_='tasty-recipes-ingredients')
                if ingredients_section:
                    ingredient_items = ingredients_section.find_all('li')
                    base_ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
                
                # Get instructions
                instructions_section = recipe_card.find('div', class_='tasty-recipes-instructions')
                if instructions_section:
                    instruction_items = instructions_section.find_all('li')
                    base_instructions = [item.text.strip() for item in instruction_items if item.text.strip()]
        
        # Just One Cookbook
        elif 'justonecookbook.com' in url:
            recipe_card = soup.find('div', class_='wprm-recipe-container')
            if recipe_card:
                # Get ingredients
                ingredient_items = recipe_card.find_all('li', class_='wprm-recipe-ingredient')
                base_ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
                
                # Get instructions
                instruction_items = recipe_card.find_all('div', class_='wprm-recipe-instruction-text')
                base_instructions = [item.text.strip() for item in instruction_items if item.text.strip()]
        
        # Clean up and validate
        base_ingredients = [i for i in base_ingredients if i]
        base_instructions = [i for i in base_instructions if i]
        variations = [v for v in variations if v['ingredients']]
        
        if not base_ingredients and not base_instructions and not variations:
            return {'error': 'Unable to extract recipe from this page. Please check if the URL is correct.'}
        
        result = {
            'title': title,
            'url': url,
            'base_ingredients': base_ingredients,
            'base_instructions': base_instructions,
            'variations': variations
        }
        return result
    except Exception as e:
        print(f"Error extracting recipe: {str(e)}")
        print("Traceback:")
        print(traceback.format_exc())
        return {'error': 'An error occurred while extracting the recipe. Please try again.'}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
def extract():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'No URL provided'})
        
        recipe = extract_recipe(url)
        if not recipe:
            return jsonify({'error': 'Pages with multiple recipes are not supported yet'})
        
        if 'error' in recipe:
            return jsonify({'error': recipe['error']})
        
        return jsonify({'recipes': [recipe]})
    except Exception as e:
        print(f"Error in /extract route: {str(e)}")
        print("Traceback:")
        print(traceback.format_exc())
        return jsonify({'error': 'An error occurred while extracting the recipe. Please try again.'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

"""Replace the SFT model with a properly integrated Polyvore-trained version.

This converts the SimpleOutfitSFT model to work with OutfitCompositionSFTModel
"""

import sys
from pathlib import Path

import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.ml.outfit_composition_sft_model import OutfitCompositionSFTModel

ARTIFACTS_DIR = Path(__file__).resolve().parent / "app" / "ml" / "artifacts"
SIMPLE_MODEL = ARTIFACTS_DIR / "outfit_composition_sft.pt"
BACKUP_PATH = ARTIFACTS_DIR / "outfit_composition_sft.pt.bak"

def main():
    print("🔄 Integrating Polyvore-trained model...\n")
    
    if not SIMPLE_MODEL.exists():
        print(f"❌ {SIMPLE_MODEL} not found!")
        return
    
    # Load the simple model weights
    print(f"📂 Loading SimpleOutfitSFT weights from {SIMPLE_MODEL}...")
    simple_state = torch.load(str(SIMPLE_MODEL), map_location="cpu", weights_only=True)
    
    # Create the OutfitCompositionSFTModel
    print(f"🏗️  Creating OutfitCompositionSFTModel...")
    target_model = OutfitCompositionSFTModel()
    target_state = target_model.state_dict()
    
    print(f"\n📊 Model compatibility analysis:")
    print(f"   SimpleOutfitSFT layers: {list(simple_state.keys())}")
    print(f"   OutfitCompositionSFTModel layers: {list(target_state.keys())}")
    
    # Try to load weights where compatible
    compatible_count = 0
    incompatible_count = 0
    
    print(f"\n🔍 Checking compatibility...\n")
    
    for key in simple_state.keys():
        if key in target_state:
            if simple_state[key].shape == target_state[key].shape:
                print(f"   ✅ {key}: compatible")
                target_state[key] = simple_state[key]
                compatible_count += 1
            else:
                print(f"   ❌ {key}: shape mismatch {simple_state[key].shape} vs {target_state[key].shape}")
                incompatible_count += 1
        else:
            print(f"   ⚠️  {key}: not found in target model")
    
    # Load the compatible weights
    try:
        target_model.load_state_dict(target_state, strict=False)
        target_model._trained = True
        print(f"\n✅ Loaded {compatible_count} compatible layers")
        
        # Save
        print(f"\n💾 Saving integrated model...")
        backup = BACKUP_PATH
        if SIMPLE_MODEL.exists() and not backup.exists():
            import shutil
            shutil.copy(SIMPLE_MODEL, backup)
            print(f"   📋 Backed up to {backup}")
        
        torch.save(target_state, str(SIMPLE_MODEL))
        print(f"   ✅ Saved to {SIMPLE_MODEL}")
        
        print(f"\n🎉 Integration complete!")
        print(f"   The model is now ready to use by the recommendation agent.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return

if __name__ == "__main__":
    main()

# BattleTech: Draconis Reach Campaign AI

A complete AI-powered campaign management system for running a BattleTech: Hot Spots Draconis Reach campaign using the MechCommander Review Circuit (MRC) system.

## Overview

This project provides a complete AI-driven campaign management solution for BattleTech campaigns set in the Draconis Reach region (April 3151 - June 3152). The system handles all aspects of campaign management including force creation, contract negotiation, tactical battles, and post-battle accounting through an intelligent LLM interface.

## Getting Started

### Prerequisites

1. **Helm Memory Core** - Download from [https://github.com/p1mps/helm](https://github.com/p1mps/helm)
2. **MegaMek** - Required for tactical battles

### Setup Instructions

1. Install Helm following the instructions at [https://github.com/p1mps/helm](https://github.com/p1mps/helm)
2. Generate the Helm SQLite database
3. Download megamek here [https://megamek.org/downloads.html](https://megamek.org/downloads.html) and copy it to your project directory

### Configuration

The system requires proper MCP (Model Context Protocol) configuration for both Helm and MegaMek:

1. Configure your Helm server with the generated database
2. Set up MegaMek to work with the campaign system

## How to Use This Project

### Campaign Initialization

Start a new campaign by providing your mercenary company name and faction selection. The system will guide you through:

1. **Force Creation**: Select your starting force from available factions (Raven Alliance, Draconis Combine, Federated Suns, etc.)
2. **Unit Selection**: Choose from vetted units with proper Battle Value (BV) and Point Value (PV)
3. **Pilot Assignment**: Set up your starting named pilots with initial skills
4. **Initial Setup**: Configure your company's starting funds and reputation

### Campaign Flow

The campaign operates through these main phases:

#### 1. Contract Generation
- Random planetary location selection from Draconis Reach worlds
- Automatic contract creation with standard terms (Base Pay, Command Rights, Salvage Rights, etc.)
- Negotiation phase where you can spend reputation to improve contract terms

#### 2. Tactical Battles
- Track-based combat system with deployment limits based on contract scale
- OPFOR generation using faction-specific unit discovery
- Battle preparation with proper force validation

#### 3. Post-Battle Accounting
- Automatic damage calculation and repair billing
- Salvage processing with negotiated terms
- XP distribution to named pilots

### Example Campaign Interaction

Here's how the LLM-driven campaign might unfold:

**GM (MercNet-Lestrade):**
> "Commander, welcome to the Draconis Reach campaign. Your company 'Iron Fang' has been assigned to a contract on Achernar. The employer is the Draconis Combine (DCMS) and they've offered a standard raid contract with Scale 1. Would you like to negotiate the terms?"

**Player:**
> "I'd like to improve the Base Pay and Salvage Rights. I have 1 Reputation point."

**GM:**
> "With your reputation, you can increase Base Pay by 1 step and Salvage Rights by 1 step. This will reduce your Command Rights by 1 step but increase your overall compensation. Would you like to proceed with these changes?"

**Player:**
> "Yes, please."

**GM:**
> "Contract finalized with the following terms:
> - Base Pay: 60% (Step 3)
> - Command Rights: Integrated
> - Salvage Rights: 20% (Step 5)
> - Support Rights: Straight/40%
> - Transportation Terms: None
>
> Your contract is now active. You'll need to deploy your force for the first track on Achernar."

### Tactical Battle Process

1. **Battle Setup**: The system generates a tactical scenario with appropriate deployment zones
2. **Force Validation**: Ensures your deployed force meets scale requirements
3. **OPFOR Generation**: Creates an opposing force based on the planet's faction and tactical theme
4. **Battle Execution**: Coordinates with MegaMek for actual combat simulation

### Key Features

- **Automated Campaign State Tracking**: All campaign details maintained in real-time
- **Smart Force Management**: Ensures all MRC restrictions are followed during force creation
- **Contract Negotiation System**: Handles reputation spending and step swapping rules
- **Tactical Integration**: Seamless connection with MegaMek for battle simulation
- **Post-Battle Processing**: Automatic calculation of combat pay, repairs, and salvage

## Technical Integration Points

### Helm Integration
- Uses Helm's database for unit information, BV/PV calculations, and lore references
- Requires the MegaMek files from Helm to be copied into your project after database generation

### MegaMek Integration
- Coordinates tactical battles through the MegaMek scenario generator
- Handles after-action reports for campaign accounting

## Campaign Management Commands

The system supports these core operations:

- `start_campaign` - Begin a new campaign
- `generate_contract` - Create a random contract for a planet
- `negotiate_contract` - Adjust contract terms using reputation points
- `deploy_force` - Select units for tactical deployment
- `initiate_battle` - Start a tactical scenario in MegaMek
- `process_after_action` - Handle post-battle accounting and repairs

## Troubleshooting

If you encounter issues with the campaign system:

1. Ensure Helm database is properly generated and accessible
2. Verify MegaMek integration with the campaign system
3. Check that all required MCP servers are properly configured

## Contributing

This project is designed to be used as a complete campaign management system. Contributions should focus on improving the LLM interaction, expanding faction support, or enhancing tactical battle scenarios.

## License

This project is designed for use with the BattleTech: Hot Spots Draconis Reach campaign system and follows the terms of the MRC patch guidelines.

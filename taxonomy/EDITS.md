# Editor's changes to the domain files

## Pass 1: one owner per task

Each row removes a task that another domain also modeled. Its products and tools were added to the task that keeps it, and the losing capability now points at the keeper.

| Removed | Kept in | Why |
|---|---|---|
| `simulate.design_exploration.tolerance_analysis` Tolerance stack-up analysis | `design.product_definition.tolerance_analysis` | tolerancing is part of the product definition |
| `produce.metrology.tolerance_stackup` Tolerance stack-up analysis | `design.product_definition.tolerance_analysis` | tolerancing is part of the product definition |
| `produce.process_planning.manufacturability_analysis` Manufacturability analysis | `design.product_definition.manufacturability_review` | the review is of the design |
| `design.estimating.parametric_cost` Parametric and should-cost estimating | `produce.process_planning.cost_estimation` | product cost follows the process plan; design.estimating keeps construction |
| `produce.additive_prep.mesh_repair` Mesh preparation and repair | `design.geometry_exchange.tessellation_mesh_repair` | same operation on the same data |
| `earth.mining.ventilation` Mine ventilation planning | `simulate.pipe_networks.ventilation_network` | an engineered network |
| `earth.atmosphere.emissions_inventory` Air emissions estimation | `operate.environmental_compliance.emissions_calculation` | emission inventories are a compliance function |
| `move.supply_chain_planning.spare_parts_provisioning` Spare parts provisioning for availability | `operate.asset_strategy.spares_optimization` | spares follow the asset strategy |
| `computing.operating_systems.screen_access` Screen reading and magnification | `learn.assistive_access.screen_reading` | assistive technology has one home |
| `computing.storage.file_sync` File synchronization and sharing | `enterprise.communication.file_sharing` | an end-user collaboration function |
| `media.web_publishing.wiki` Collaborative wiki authoring | `enterprise.documents.knowledge_base` | same function |
| `enterprise.authoring.speech_dictation` Speech dictation to text | `media.language.speech_transcription` | recognition is one function wherever it is used |
| `media.vector_graphics.diagramming` Diagrams and mind maps | `enterprise.process_workflow.diagramming` | same function |
| `enterprise.communication.appointment_booking` Client appointment booking | `commerce.service_scheduling.appointment_booking` | customer-facing booking |
| `govern.legal_practice.document_assembly` Legal document assembly | `enterprise.documents.document_assembly` | same function, legal templates are one use |
| `govern.legal_practice.legal_billing` Legal time capture and billing | `enterprise.receivables_payables.time_billing` | same function |
| `govern.social_services.transferable_skills` Vocational transferable-skills analysis | `learn.career_guidance.transferable_skills` | same function |
| `govern.law_enforcement.digital_evidence` Digital evidence examination | `computing.security_operations.digital_forensics` | same function |
| `commerce.point_of_sale.payment_fraud_screening` Merchant payment fraud screening | `govern.compliance_financial_crime.payment_fraud` | same function |
| `move.travel_reservation.itinerary_packaging` Tour and itinerary packaging | `commerce.hospitality.tour_activity_booking` | tours sit with hospitality; move keeps transport reservation |
| `commerce.merchandising.store_replenishment` Store demand forecasting and replenishment | `move.supply_chain_planning.demand_forecasting` | same forecasting problem |
| `science.social_research.psychometric_calibration` Psychometric item calibration | `learn.assessment.psychometric_calibration` | same function |
| `enterprise.process_workflow.no_code_apps` No-code tables and forms | `computing.databases.desktop_databases` | same function |
| `operate.electrical_testing.instrument_calibration` Field instrument calibration management | `produce.metrology.gauge_calibration_management` | same function |
| `commerce.service_scheduling.repair_orders` Repair and service order tracking | `operate.maintenance_management.repair_orders` | same function |
| `commerce.customer_relationship.record_matching` Customer record deduplication | `computing.data_integration.master_data` | entity resolution is a general data function |
| `learn.classroom_interaction.dynamic_mathematics` Dynamic mathematics manipulatives | `science.symbolic_math.interactive_geometry` | same tools |
| `enterprise.authoring.audience_polling` Live audience polling and questions | `learn.classroom_interaction.audience_response` | same function |
| `enterprise.projects.effort_estimation` Parametric effort and cost estimation | `computing.requirements_design.effort_estimation` | the products are software estimators; construction and product costing have their own nodes |
| `produce.process_specific_prep.print_preflight` Print preflight | `media.page_layout.pdf_preflight` | same check on the same file |
| `learn.course_delivery.virtual_classroom` Virtual classroom sessions | `enterprise.communication.video_meetings` | same function |

## Pass 1: renames

| Task | Was | Now | Why |
|---|---|---|---|
| `operate.condition_monitoring.data_historian` | Operating data historian and rounds | Operator rounds and inspection data | the historian itself is produce.supervisory_control |
| `produce.supervisory_control.loop_tuning_monitoring` | Control loop tuning and performance monitoring | Control loop performance monitoring | tuning design is simulate.system_dynamics |
| `enterprise.documents.scan_ocr` | Scanning and text recognition | Document scanning and capture | recognition itself is media.language |
| `govern.legal_practice.contract_management` | Contract review and lifecycle management | Contract review and clause analysis | lifecycle management is enterprise.procurement |
| `govern.public_administration.customs_declaration` | Customs declaration and tariff classification | Customs declaration processing and risk targeting | the trader's side is move.trade_compliance |
| `govern.law_enforcement.scene_reconstruction` | Crime scene and collision diagramming and reconstruction | Crime scene and collision diagramming | reconstruction physics is simulate.vehicle_vessel |
| `produce.metrology.gauge_calibration_management` | Gauge and calibration management | Gauge and instrument calibration management | now also holds field instrument calibration |

## Pass 1: additions

- `simulate.semiconductor_device` (process, device and lithography simulation). Design handed it to simulate and simulate handed it to design, so neither had it. Written by the editor.

## Pass 2: cross-references

The authors wrote `see_also` before they could see each other's files. 229 references to guessed ids were repointed at the real capability and 15 with no counterpart were dropped (mapping in `input/see_also_map.tsv`, with ten editor's corrections).

## Pass 3: crosswalk verification

Each domain's crosswalk was checked against the published source by a separate agent (`verify/*.json`, method in `VERIFY.md`). Only entries whose source page was read are marked `fetched`; everything else is `memory`.

Totals: {'confirmed': 890, 'corrected': 192, 'contradicted': 11, 'unverifiable': 721}

| Node | Scheme | Was | Now |
|---|---|---|---|
| `commerce.customer_relationship.lead_pipeline` | APQC PCF cross-industry v7 |  Generate leads | 3.5.1 Manage leads/opportunities |
| `commerce.customer_relationship.territory_quota` | APQC PCF cross-industry v7 |  Manage sales force | removed: not in the scheme |
| `commerce.customer_relationship.configure_price_quote` | APQC PCF cross-industry v7 |  Manage customer sales | 3.5.3 Develop and manage sales proposals, bids, and quotes |
| `commerce.advertising` | IAB Tech Lab |  OpenRTB real-time bidding protocol |  OpenRTB (Real-Time Bidding) |
| `commerce.advertising.ad_serving` | IAB Tech Lab |  VAST video ad serving template |  Digital Video Ad Serving Template (VAST) |
| `computing.languages.dynamic_interpreters` | ACM CCS 2012 |  Software and its engineering > Software notations and tools > Interpreters | 10011007.10011006.10011041.10010943 Software and its engineering > Software notations and tools > Compilers > Interpreters |
| `computing.languages.interface_codegen` | ACM CCS 2012 |  Software and its engineering > Software notations and tools > Source code generation | 10011007.10011006.10011041.10011047 Software and its engineering > Software notations and tools > Compilers > Source code generation |
| `computing.languages.source_translation` | ACM CCS 2012 |  Software and its engineering > Software creation and management > Software post-development issues > Software reengineering | removed: no concept with this name in CCS 2012 file |
| `computing.dev_tooling.ai_code_generation` | ACM CCS 2012 |  Software and its engineering > Software notations and tools > Source code generation | 10011007.10011006.10011041.10011047 Software and its engineering > Software notations and tools > Compilers > Source code generation |
| `computing.dev_tooling.version_control` | ACM CCS 2012 |  Software and its engineering > Software creation and management > Software version control | 10011007.10011074.10011111.10011695 Software and its engineering > Software creation and management > Software post-development issues > Software version control |
| `computing.testing.debugging` | ACM CCS 2012 |  Software and its engineering > Software creation and management > Software verification and validation > Software testing and debugging | 10011007.10011074.10011099.10011102.10011103 Software and its engineering > Software creation and management > Software verification and validation > Software defect analysis > Software testing and debugging |
| `computing.embedded` | ACM CCS 2012 |  Computer systems organization > Embedded and cyber-physical systems > Embedded software | 10010520.10010553.10010562.10010564 Computer systems organization > Embedded and cyber-physical systems > Embedded systems > Embedded software |
| `computing.embedded.cross_compilation` | ACM CCS 2012 |  Computer systems organization > Embedded and cyber-physical systems > Embedded software | 10010520.10010553.10010562.10010564 Computer systems organization > Embedded and cyber-physical systems > Embedded systems > Embedded software |
| `computing.databases` | NICE Framework work role |  Database Administrator | IO-WRL-002 Database Administration |
| `computing.databases.administration_tuning` | NICE Framework work role |  Database Administrator | IO-WRL-002 Database Administration |
| `computing.data_integration` | ACM CCS 2012 |  Information systems > Information integration | 10002951.10002952.10003219 Information systems > Data management systems > Information integration |
| `computing.data_integration` | ACM CCS 2012 |  Information systems > Information integration > Extraction, transformation and loading | 10002951.10002952.10003219.10003215 Information systems > Data management systems > Information integration > Extraction, transformation and loading |
| `computing.data_integration.etl` | ACM CCS 2012 |  Information systems > Information integration > Extraction, transformation and loading | 10002951.10002952.10003219.10003215 Information systems > Data management systems > Information integration > Extraction, transformation and loading |
| `computing.operating_systems` | NICE Framework work role |  System Administrator | IO-WRL-005 Systems Administration |
| `computing.networking` | ACM CCS 2012 |  Networks > Network management | 10003033.10003099.10003104 Networks > Network services > Network management |
| `computing.networking` | ACM CCS 2012 |  Networks > Network monitoring | 10003033.10003099.10003105 Networks > Network services > Network monitoring |
| `computing.networking` | ACM CCS 2012 |  Networks > Network protocols > Routing protocols | 10003033.10003039.10003045.10003046 Networks > Network protocols > Network layer protocols > Routing protocols |
| `computing.networking` | NICE Framework work role |  Network Operations Specialist | IO-WRL-004 Network Operations |
| `computing.networking.routing_switching` | ACM CCS 2012 |  Networks > Network protocols > Routing protocols | 10003033.10003039.10003045.10003046 Networks > Network protocols > Network layer protocols > Routing protocols |
| `computing.networking.network_monitoring` | ACM CCS 2012 |  Networks > Network monitoring | 10003033.10003099.10003105 Networks > Network services > Network monitoring |
| `computing.security_operations` | NICE Framework work role |  Vulnerability Assessment Analyst | PD-WRL-007 Vulnerability Analysis |
| `computing.security_operations` | NICE Framework work role |  Cyber Defense Analyst | PD-WRL-001 Defensive Cybersecurity |
| `computing.security_operations` | NICE Framework work role |  Cyber Defense Forensics Analyst | PD-WRL-002 Digital Forensics |
| `computing.security_operations` | NICE Framework work role |  Cyber Defense Incident Responder | PD-WRL-003 Incident Response |
| `computing.security_operations.digital_forensics` | NICE Framework work role |  Cyber Defense Forensics Analyst | PD-WRL-002 Digital Forensics |
| `design.solid_modeling` | ISO 10303 (STEP) | AP203 Configuration controlled 3D design of mechanical parts and assemblies | AP203 Configuration Controlled Design |
| `design.solid_modeling.freeform_surfacing` | ISO 10303 (STEP) | AP216 Ship moulded forms | AP216 Ship Moulded Form |
| `design.geometry_exchange.neutral_translation` | ISO 10303 (STEP) | AP214 Core data for automotive mechanical design processes | AP214 Automotive Design |
| `design.geometry_exchange.feature_recognition` | ISO 10303 (STEP) | AP224 Mechanical product definition for process planning using machining features | AP224 Feature-Based Process Planning |
| `design.plant_services` | ISO 10303 (STEP) | AP221 Functional data and their schematic representation for process plants | AP221 Functional Data and Schematics for Process Plant |
| `design.plant_services.pid_authoring` | DEXPI |  Data Exchange in the Process Industry (P&ID exchange specification) |  DEXPI: common data exchange standard for the process industry, focused on P&IDs |
| `design.plant_services.pipe_routing` | ISO 10303 (STEP) | AP227 Plant spatial configuration (piping) | AP227 Plant Spatial Configuration |
| `earth.surveying.bathymetry` | IHO standards | S-44 Standards for Hydrographic Surveys | S-44 IHO Standards for Hydrographic Surveys |
| `enterprise.receivables_payables.receivables_collections` | APQC PCF Cross-Industry v7 |  Process accounts receivable | 9.2.3 Process accounts receivable (AR) |
| `enterprise.receivables_payables.payables_matching` | APQC PCF Cross-Industry v7 |  Process accounts payable | 9.6.1 Process accounts payable (AP) |
| `enterprise.financial_planning.budgeting` | APQC PCF Cross-Industry v7 |  Perform budgeting | 9.1.1 Perform planning/budgeting/forecasting |
| `enterprise.payroll_time.payroll_tax_filing` | APQC PCF Cross-Industry v7 |  Process payroll taxes | 9.5.3 Manage and process payroll taxes |
| `enterprise.hr_admin.performance_reviews` | APQC PCF Cross-Industry v7 |  Develop and counsel employees | 7.3.2 Manage employee performance |
| `enterprise.procurement.spend_analysis` | APQC PCF Cross-Industry v7 |  Develop sourcing strategies | 4.2.1 Provide sourcing governance and perform category management |
| `enterprise.authoring` | ACM CCS 2012 |  Applied computing > Document management and text processing > Document preparation > Text editing | 10010405.10010497.10010500.10010501 Applied computing > Document management and text processing > Document management > Text editing |
| `enterprise.authoring.proofreading` | ACM CCS 2012 |  Applied computing > Document management and text processing > Document preparation > Text editing | 10010405.10010497.10010500.10010501 Applied computing > Document management and text processing > Document management > Text editing |
| `enterprise.spreadsheets` | OASIS |  OpenDocument Formula (OpenFormula), ODF 1.2 Part 2 |  OpenDocument v1.2 Part 2: Recalculated Formula (OpenFormula) Format |
| `enterprise.spreadsheets.formula_calculation` | OASIS |  OpenDocument Formula (OpenFormula), ODF 1.2 Part 2 |  OpenDocument v1.2 Part 2: Recalculated Formula (OpenFormula) Format |
| `govern.risk_actuarial` | BIAN Service Landscape |  Market Risk Models | removed: No MarketRisk* service domain in BIAN releases 10-14 listing |
| `govern.insurance` | EDM Council FIBO | FBC Financial Business and Commerce: insurance | FBC Financial Business and Commerce |
| `govern.compliance_financial_crime` | OCEG GRC Capability Model |  Governance, risk and compliance |  GRC Capability Model |
| `govern.compliance_financial_crime` | BIAN Service Landscape |  Fraud Detection |  Fraud Diagnosis |
| `govern.compliance_financial_crime.controls_management` | OCEG GRC Capability Model |  Governance, risk and compliance |  GRC Capability Model |
| `govern.compliance_financial_crime.payment_fraud` | BIAN Service Landscape |  Fraud Detection |  Fraud Diagnosis |
| `govern.legal_research` | LEDES UTBMS code sets |  Activity code: research | A102 Research |
| `govern.courts_corrections.court_case_management` | NIEM domains |  Justice: court case filing |  Justice |
| `govern.social_services` | NIEM domains |  Children, Youth, and Family Services | removed: Domain list: Agriculture, Biometrics, CBRN, Emergency Management, Human Services, ... no CYFS |
| `govern.public_administration` | UN COFOG | 01.1 General public services: financial and fiscal affairs | 01.1 Executive and legislative organs, financial and fiscal affairs, external affairs |
| `govern.public_administration` | UN COFOG | 01.1 Executive and legislative organs | 01.1.1 Executive and legislative organs |
| `govern.public_administration.elections` | US EAC Voluntary Voting System Guidelines |  Voting system requirements |  Voluntary Voting System Guidelines |
| `govern.public_administration.legislative_drafting` | Akoma Ntoso (OASIS LegalDocML) |  Legislative document model |  LegalDocumentML (Akoma Ntoso) |
| `health.clinical_record` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.2 Client health records | 2.2 Person-centred health records |
| `health.clinical_record` | ACM CCS 2012 |  Health care information systems | 10010405.10010444.10010447 Applied computing > Life and medical sciences > Health care information systems |
| `health.clinical_record.nursing_flowsheets` | IHE |  Patient Care Device: Device Enterprise Communication |  Devices (DEV): Device Enterprise Communication (DEC) |
| `health.clinical_record.perioperative_record` | IHE |  Patient Care Device: Device Enterprise Communication |  Devices (DEV): Device Enterprise Communication (DEC) |
| `health.orders_coordination.diagnostic_order_entry` | ONC Health IT Certification (45 CFR 170.315) | (a)(2) CPOE - laboratory | (a)(2) Computerized provider order entry—laboratory |
| `health.orders_coordination.diagnostic_order_entry` | ONC Health IT Certification (45 CFR 170.315) | (a)(3) CPOE - diagnostic imaging | (a)(3) Computerized provider order entry—diagnostic imaging |
| `health.orders_coordination.results_management` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.10.1 Transmit diagnostic result to healthcare provider | 2.10.1 Transmit person's diagnostic result to healthcare provider |
| `health.orders_coordination.referral_management` | ISO/HL7 10781 EHR System Functional Model R2 |  Manage Referrals | CP.4.6 Manage Orders for Referral |
| `health.medication.order_interaction_checking` | ONC Health IT Certification (45 CFR 170.315) | (a)(1) CPOE - medications | (a)(1) Computerized provider order entry—medications |
| `health.medication.pharmacy_dispensing` | IHE |  Pharmacy: Pharmacy Dispense |  Pharmacy: Community Dispense (DIS) |
| `health.medication.administration_record` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.9.2 Track client's medication consumption | 2.9.2 Track individual's medication consumption |
| `health.decision_support` | ISO/HL7 10781 EHR System Functional Model R2 |  Care Provision Support | CP Care Provision |
| `health.decision_support.risk_scores` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.3.3 Screen clients by risk or other health status | 2.3.3 Screen persons by risk or other health status |
| `health.decision_support.symptom_triage` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.3.3 Screen clients by risk or other health status | 2.3.3 Screen persons by risk or other health status |
| `health.patient_administration` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.1 Client identification and registration | 2.1 Identification and registration of persons |
| `health.patient_administration` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.7 Health worker activity planning and scheduling | 2.7 Scheduling and activity planning for healthcare providers |
| `health.patient_administration.registration` | ONC Health IT Certification (45 CFR 170.315) | (a)(5) Demographics | (a)(5) Patient demographics and observations |
| `health.patient_administration.registration` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.1.2 Enrol client for health services/clinical care plan | 2.1.2 Enrol person(s) for health services/clinical care plan |
| `health.patient_administration.identity_matching` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.1.1 Verify client unique identity | 2.1.1 Verify a person's unique identity |
| `health.patient_administration.appointment_scheduling` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.7 Health worker activity planning and scheduling | 2.7 Scheduling and activity planning for healthcare providers |
| `health.revenue_cycle` | WHO Classification of Digital Health Interventions v1.0 (2018) | 3.5 Health financing | 3.5 Health system financial management |
| `health.revenue_cycle.claim_submission_remittance` | WHO Classification of Digital Health Interventions v1.0 (2018) | 3.5 Health financing | 3.5 Health system financial management |
| `health.imaging` | ACM CCS 2012 |  Health informatics | 10010405.10010444.10010449 Applied computing > Life and medical sciences > Health informatics |
| `health.physiological_signals` | IHE |  Patient Care Device |  Devices (DEV) |
| `health.physiological_signals.bedside_monitoring` | IHE |  Patient Care Device: Alarm Communication Management |  Devices (DEV): Alert Communication Management (ACM) |
| `health.laboratory.transfusion` | ISO/HL7 10781 EHR System Functional Model R2 |  Manage Orders for Blood Products and Biologics | CP.4.5 Manage Orders for Blood Products and Other Biologics |
| `health.laboratory.slide_image_analysis` | DICOM |  Whole Slide Microscopy |  VL Whole Slide Microscopy Image IOD |
| `health.therapy_planning` | ACM CCS 2012 |  Health informatics | 10010405.10010444.10010449 Applied computing > Life and medical sciences > Health informatics |
| `health.therapy_planning.rt_delivery_record` | IHE |  Radiation Oncology: Integrated Positioning and Delivery |  Radiation Oncology: Treatment Delivery Workflow-II (TDW-II) |
| `health.psych_assessment.symptom_scales` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.3.3 Screen clients by risk or other health status | 2.3.3 Screen persons by risk or other health status |
| `health.remote_care` | WHO Classification of Digital Health Interventions v1.0 (2018) | 1.1 Targeted client communication | 1.1 Targeted communication to Persons |
| `health.remote_care` | ACM CCS 2012 |  Consumer health | 10010405.10010444.10010446 Applied computing > Life and medical sciences > Consumer health |
| `health.remote_care.virtual_visit` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.4.1 Consultations between remote client and healthcare provider | 2.4.1 Consultations between remote person and healthcare provider |
| `health.remote_care.remote_monitoring` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.4.2 Remote monitoring of client health or diagnostic data by provider | 2.4.2 Remote monitoring of person's health or diagnostic data by provider |
| `health.remote_care.teleconsultation` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.4.4 Consultations for case management between healthcare provider(s) | 2.4.4 Consultations for case management between healthcare providers |
| `health.remote_care.patient_portal` | WHO Classification of Digital Health Interventions v1.0 (2018) | 1.4.1 Access by client to own medical records | 1.4.1 Access by the individual to own medical or summary health records |
| `health.remote_care.patient_outreach` | WHO Classification of Digital Health Interventions v1.0 (2018) | 1.1 Targeted client communication | 1.1 Targeted communication to Persons |
| `health.remote_care.patient_reported_outcomes` | WHO Classification of Digital Health Interventions v1.0 (2018) | 1.4.3 Active data capture/documentation by client | 1.4.3 Active data capture/documentation by an individual |
| `health.population_health` | ONC Health IT Certification (45 CFR 170.315) | (f) Public health transmission criteria | (f) Public health |
| `health.population_health.immunization_registry` | ISO/HL7 10781 EHR System Functional Model R2 |  Immunization Management | CP.6.2 Manage Immunization Administration |
| `health.clinical_research` | ACM CCS 2012 |  Health informatics | 10010405.10010444.10010449 Applied computing > Life and medical sciences > Health informatics |
| `health.clinical_research.signal_detection` | WHO Classification of Digital Health Interventions v1.0 (2018) | 2.9.3 Report adverse drug events | 2.9.3 Report adverse drug effects |
| `learn.special_education` | Ed-Fi |  Special education program association |  Special Education Data Model Domain |
| `learn.library_management` | ACM CCS 2012 |  Applied computing > Document management and text processing > Digital libraries and archives | 10002951.10003227.10003392 Information systems > Information systems applications > Digital libraries and archives |
| `learn.library_management.subject_indexing` | NISO | Z39.19 Guidelines for monolingual controlled vocabularies | Z39.19 Guidelines for the Construction, Format, and Management of Monolingual Controlled Vocabularies |
| `learn.library_management.electronic_resources` | NISO | Z39.88 OpenURL Framework | Z39.88 The OpenURL Framework for Context-Sensitive Services |
| `media.raster_imaging.raw_development` | ACM CCS 2012 |  Computational photography | 10010147.10010371.10010382.10010236 Computing methodologies > Computer graphics > Image manipulation > Computational photography |
| `media.raster_imaging.retouching_compositing` | ACM CCS 2012 |  Image manipulation > Image processing | 10010147.10010371.10010382.10010383 Computing methodologies > Computer graphics > Image manipulation > Image processing |
| `media.raster_imaging.restoration_enhancement` | ACM CCS 2012 |  Image manipulation > Image processing | 10010147.10010371.10010382.10010383 Computing methodologies > Computer graphics > Image manipulation > Image processing |
| `media.raster_imaging.multi_image_merge` | ACM CCS 2012 |  Computational photography | 10010147.10010371.10010382.10010236 Computing methodologies > Computer graphics > Image manipulation > Computational photography |
| `media.vector_graphics.tracing` | ACM CCS 2012 |  Document capture > Graphics recognition and interpretation | 10010405.10010497.10010504.10010507 Applied computing > Document management and text processing > Document capture > Graphics recognition and interpretation |
| `media.page_layout.interactive_layout` | ACM CCS 2012 |  Document preparation > Format and notation | 10010405.10010497.10010510.10010514 Applied computing > Document management and text processing > Document preparation > Format and notation |
| `media.page_layout.markup_typesetting` | ACM CCS 2012 |  Document preparation > Markup languages | 10002951.10003260.10003309.10010512 Information systems > World Wide Web > Web data description languages > Markup languages |
| `media.page_layout.markup_typesetting` | W3C |  Extensible Stylesheet Language Formatting Objects (XSL-FO) |  Extensible Stylesheet Language (XSL) Version 1.1 |
| `media.video_post` | SMPTE |  Post-production technology area | removed: Technology Committees listed; none is post-production |
| `media.video_post.nonlinear_editing` | SMPTE |  Edit decision lists and timecode (SMPTE ST 12) | ST 12 SMPTE Time and Control Code |
| `media.video_post.compositing_keying` | ACM CCS 2012 |  Image manipulation > Image processing; Matting | removed: missing part(s): Image manipulation > Image processing; Image manipulation > Matting |
| `media.video_post.camera_tracking` | ACM CCS 2012 |  Computing methodologies > Computer vision > Computer vision problems > Tracking | 10010147.10010178.10010224.10010245.10010253 Computing methodologies > Artificial intelligence > Computer vision > Computer vision problems > Tracking |
| `media.three_d_animation.polygon_modeling` | ACM CCS 2012 |  Shape modeling > Mesh models | 10010147.10010371.10010396.10010397 Computing methodologies > Computer graphics > Shape modeling > Mesh models |
| `media.three_d_animation.sculpting` | ACM CCS 2012 |  Shape modeling > Mesh models | 10010147.10010371.10010396.10010397 Computing methodologies > Computer graphics > Shape modeling > Mesh models |
| `media.three_d_animation.texturing_lookdev` | ACM CCS 2012 |  Rendering > Texturing | 10010147.10010371.10010382.10010384 Computing methodologies > Computer graphics > Image manipulation > Texturing |
| `media.three_d_animation.environment_generation` | ACM CCS 2012 |  Shape modeling > Procedural modeling | removed: no concept with this name in CCS 2012 file |
| `media.three_d_animation.rigging` | ACM CCS 2012 |  Animation > Motion processing | 10010147.10010371.10010352.10010380 Computing methodologies > Computer graphics > Animation > Motion processing |
| `media.three_d_animation.keyframe_animation` | ACM CCS 2012 |  Computer graphics > Animation | 10010147.10010371.10010352 Computing methodologies > Computer graphics > Animation |
| `media.three_d_animation.motion_capture` | ACM CCS 2012 |  Animation > Motion capture | 10010147.10010371.10010352.10010238 Computing methodologies > Computer graphics > Animation > Motion capture |
| `media.rendering_effects` | ACM CCS 2012 |  Computer graphics > Animation > Physical simulation | 10010147.10010371.10010352.10010379 Computing methodologies > Computer graphics > Animation > Physical simulation |
| `media.rendering_effects.offline_rendering` | ACM CCS 2012 |  Rendering > Ray tracing | 10010147.10010371.10010372.10010374 Computing methodologies > Computer graphics > Rendering > Ray tracing |
| `media.rendering_effects.real_time_rendering` | ACM CCS 2012 |  Rendering > Rasterization | 10010147.10010371.10010372.10010373 Computing methodologies > Computer graphics > Rendering > Rasterization |
| `media.rendering_effects.fx_simulation` | ACM CCS 2012 |  Animation > Physical simulation | 10010147.10010371.10010352.10010379 Computing methodologies > Computer graphics > Animation > Physical simulation |
| `media.rendering_effects.crowd_simulation` | ACM CCS 2012 |  Animation > Procedural animation | 10010147.10010371.10010352.10010378 Computing methodologies > Computer graphics > Animation > Procedural animation |
| `media.rendering_effects.view_synthesis` | ACM CCS 2012 |  Rendering > Image-based rendering | 10010147.10010371.10010382.10010385 Computing methodologies > Computer graphics > Image manipulation > Image-based rendering |
| `media.audio_production` | EBU |  Audio production technology area | removed: Areas: Media production, Media distribution, Spectrum, ...; no Audio production |
| `media.audio_production.multitrack_mixing` | ACM CCS 2012 |  Sound and music computing | 10010405.10010469.10010475 Applied computing > Arts and humanities > Sound and music computing |
| `media.audio_production.waveform_editing` | ACM CCS 2012 |  Sound and music computing | 10010405.10010469.10010475 Applied computing > Arts and humanities > Sound and music computing |
| `media.audio_production.mastering_loudness` | ITU-R | BS.1770 Algorithms to measure audio programme loudness and true-peak level | BS.1770 Algorithms to measure audio programme loudness and true-peak audio level |
| `media.audio_production.synthesis_instruments` | ACM CCS 2012 |  Sound and music computing | 10010405.10010469.10010475 Applied computing > Arts and humanities > Sound and music computing |
| `media.audio_production.source_separation` | ACM CCS 2012 |  Sound and music computing | 10010405.10010469.10010475 Applied computing > Arts and humanities > Sound and music computing |
| `media.music_notation.optical_music_recognition` | ACM CCS 2012 |  Document capture > Graphics recognition and interpretation | 10010405.10010497.10010504.10010507 Applied computing > Document management and text processing > Document capture > Graphics recognition and interpretation |
| `media.music_notation.assisted_composition` | ACM CCS 2012 |  Sound and music computing | 10010405.10010469.10010475 Applied computing > Arts and humanities > Sound and music computing |
| `media.games_interactive` | ACM CCS 2012 |  Human-centered computing > Human computer interaction > Interaction paradigms > Virtual reality | 10003120.10003121.10003124.10010866 Human-centered computing > Human computer interaction (HCI) > Interaction paradigms > Virtual reality |
| `media.games_interactive.engine_authoring` | ACM CCS 2012 |  Computer games | 10010405.10010476.10011187.10011190 Applied computing > Computers in other domains > Personal computers and PC applications > Computer games |
| `media.games_interactive.multimedia_narrative` | ACM CCS 2012 |  Document preparation > Hypertext / hypermedia creation | 10010405.10010497.10010510.10010920 Applied computing > Document management and text processing > Document preparation > Hypertext / hypermedia creation |
| `media.games_interactive.procedural_content` | ACM CCS 2012 |  Computer games | 10010405.10010476.10011187.10011190 Applied computing > Computers in other domains > Personal computers and PC applications > Computer games |
| `media.web_publishing.accessibility_evaluation` | W3C |  Accessibility Conformance Testing (ACT) Rules |  Accessibility Conformance Testing (ACT) Rules Format 1.1 |
| `media.ux_prototyping` | ACM CCS 2012 |  Human-centered computing > Human computer interaction > HCI design and evaluation methods > Usability testing | 10003120.10003121.10003122.10010854 Human-centered computing > Human computer interaction (HCI) > HCI design and evaluation methods > Usability testing |
| `media.ux_prototyping.wireframing` | ACM CCS 2012 |  Interaction design process and methods | 10003120.10003123.10010860 Human-centered computing > Interaction design > Interaction design process and methods |
| `media.ux_prototyping.interface_design` | ACM CCS 2012 |  User interface design | 10003120.10003123.10010860.10010858 Human-centered computing > Interaction design > Interaction design process and methods > User interface design |
| `media.broadcast_streaming` | EBU |  Broadcast technology areas: production, distribution, media archive |  Media production; Media distribution |
| `media.broadcast_streaming.encoding` | ACM CCS 2012 |  Computer graphics > Image compression | 10010147.10010371.10010395 Computing methodologies > Computer graphics > Image compression |
| `media.language.machine_translation` | ACM CCS 2012 |  Natural language processing > Machine translation | 10010147.10010178.10010179.10010180 Computing methodologies > Artificial intelligence > Natural language processing > Machine translation |
| `media.language.speech_transcription` | ACM CCS 2012 |  Natural language processing > Speech recognition | 10010147.10010178.10010179.10010183 Computing methodologies > Artificial intelligence > Natural language processing > Speech recognition |
| `media.language.speech_synthesis` | ITU-T | P.800 Methods for subjective determination of transmission quality (MOS) | P.800 Methods for subjective determination of transmission quality |
| `media.language.ocr` | ACM CCS 2012 |  Document capture > Optical character recognition | 10010405.10010497.10010504.10010508 Applied computing > Document management and text processing > Document capture > Optical character recognition |
| `move.supply_chain_planning.demand_forecasting` | APQC PCF cross-industry 7 |  Develop baseline forecasts | 4.1.2.1 Develop baseline demand forecasts |
| `move.supply_chain_planning.inventory_policy_optimization` | APQC PCF cross-industry 7 |  Manage inventory | 4.1.6.2 Establish inventory management constraints |
| `move.supply_chain_planning.network_design` | APQC PCF cross-industry 7 |  Design supply chain network | 4.4.1.2 Design logistics network |
| `move.warehouse_inventory.stock_records` | APQC PCF cross-industry 7 |  Manage inventory | 4.4.3.5 Track inventory accuracy |
| `move.freight_transport.carrier_procurement` | APQC PCF cross-industry 7 |  Procure transportation services | removed: not in the scheme |
| `move.parcel_mail.address_validation` | Universal Postal Union |  S42 international postal address components |  S42: International postal address components and templates |
| `move.fleet_dispatch.hours_of_service` | US 49 CFR Part 395 |  Hours of service of drivers; electronic logging devices |  Hours of service of drivers (Subpart B: Electronic Logging Devices) |
| `move.flight_operations.flight_time_logging` | US 14 CFR Part 117 |  Flight and duty limitations |  Flight and duty limitations and rest requirements: flightcrew members |
| `move.maritime.passage_planning` | IMO | Resolution MSC.232(82) ECDIS performance standards | Resolution MSC.232(82) Adoption of the revised performance standards for Electronic Chart Display and Information Systems (ECDIS) |
| `move.road_traffic` | ARC-IT |  Traffic management service packages |  Traffic Management (service package group) |
| `produce.process_planning` | IEC 62264-3 activity model |  Product definition management |  Management of product definitions |
| `produce.process_planning.manufacturing_bom_routing` | IEC 62264-3 activity model |  Product definition management |  Management of product definitions |
| `produce.supervisory_control` | ISA-101 | ANSI/ISA-101.01 Human machine interfaces for process automation | ISA-101.01-2015 Human Machine Interfaces for Process Automation Systems |
| `produce.manufacturing_execution.dispatching` | IEC 62264-3 activity model |  Production dispatching |  Dispatching production orders |
| `produce.manufacturing_execution.execution_guidance` | IEC 62264-3 activity model |  Production execution management |  Execution of production orders |
| `produce.manufacturing_execution.machine_data_collection` | IEC 62264-3 activity model |  Production data collection |  Collection of production data |
| `produce.manufacturing_execution.tracking_genealogy` | IEC 62264-3 activity model |  Production tracking |  Production track and trace |
| `produce.manufacturing_execution.labor_tracking` | IEC 62264-3 activity model |  Production resource management |  Management of resources |
| `produce.production_scheduling` | IEC 62264-3 activity model |  Detailed production scheduling |  Scheduling (production processes) |
| `produce.production_scheduling.job_shop_scheduling` | IEC 62264-3 activity model |  Detailed production scheduling |  Scheduling (production processes) |
| `science.numerical_computing.pde_solution` | MSC 2020 | 65M Numerical methods for initial value and initial-boundary value problems involving PDEs | 65M Numerical methods for partial differential equations, initial value and time-dependent initial-boundary value problems |
| `science.numerical_computing.pde_solution` | MSC 2020 | 65N Numerical methods for boundary value problems involving PDEs | 65N Numerical methods for partial differential equations, boundary value problems |
| `science.numerical_computing.interpolation_approximation` | MSC 2020 | 65D Numerical approximation and computational geometry | 65D Numerical approximation and computational geometry (primarily algorithms) |
| `science.symbolic_math.interactive_geometry` | MSC 2020 | 68U05 Computer graphics; computational geometry | 68U05 Computer graphics; computational geometry (digital and algorithmic aspects) |
| `science.statistics.mixed_models` | CRAN Task Views | MixedModels Mixed, Multilevel, and Hierarchical Models | MixedModels Mixed, Multilevel, and Hierarchical Models in R |
| `science.experimental_design.power_sample_size` | CRAN Task Views | ClinicalTrials Clinical Trial Design, Monitoring, and Analysis | ClinicalTrials Clinical Trial Design, Monitoring, Analysis and Reporting |
| `science.signal_time_series` | MSC 2020 | 62M10 Time series, auto-correlation, regression, etc. | 62M10 Time series, auto-correlation, regression, etc. in statistics (GARCH) |
| `science.machine_learning.supervised_tabular` | ACM CCS 2012 |  Machine learning > Learning paradigms > Supervised learning | 10010147.10010257.10010258.10010259 Computing methodologies > Machine learning > Learning paradigms > Supervised learning |
| `science.machine_learning.unsupervised` | ACM CCS 2012 |  Machine learning > Learning paradigms > Unsupervised learning | 10010147.10010257.10010258.10010260 Computing methodologies > Machine learning > Learning paradigms > Unsupervised learning |
| `science.machine_learning.pattern_mining` | ACM CCS 2012 |  Information systems > Data mining > Association rules | 10002951.10003227.10003351.10003443 Information systems > Information systems applications > Data mining > Association rules |
| `science.machine_learning.neural_networks` | ACM CCS 2012 |  Machine learning > Machine learning approaches > Neural networks | 10010147.10010257.10010293.10010294 Computing methodologies > Machine learning > Machine learning approaches > Neural networks |
| `science.optimization` | ACM CCS 2012 |  Mathematics of computing > Mathematical optimization | 10002950.10003714.10003716 Mathematics of computing > Mathematical analysis > Mathematical optimization |
| `science.optimization.constraint_programming` | ACM CCS 2012 |  Theory of computation > Constraint and logic programming | 10003752.10003790.10003795 Theory of computation > Logic > Constraint and logic programming |
| `science.visualization_imaging` | ACM CCS 2012 |  Human-centered computing > Visualization > Scientific visualization | 10003120.10003145.10003147.10010364 Human-centered computing > Visualization > Visualization application domains > Scientific visualization |
| `science.visualization_imaging` | ACM CCS 2012 |  Computing methodologies > Computer vision > Image segmentation | 10010147.10010178.10010224.10010245.10010247 Computing methodologies > Artificial intelligence > Computer vision > Computer vision problems > Image segmentation |
| `science.visualization_imaging.motion_tracking` | ACM CCS 2012 |  Computing methodologies > Computer vision > Tracking | 10010147.10010178.10010224.10010245.10010253 Computing methodologies > Artificial intelligence > Computer vision > Computer vision problems > Tracking |
| `science.analytical_data.chromatography` | EDAM |  Topic: Chromatography | removed: no Chromatography topic in EDAM; only operation_3628 Chromatographic alignment |
| `science.systems_biology.kinetic_modeling` | EDAM |  Operation: Simulation and modelling of biological systems | operation_2426 Modelling and simulation |
| `science.systems_biology.electrophysiology_models` | EDAM |  Topic: Electrophysiology | topic_3300 Physiology |
| `science.molecular_modeling.electronic_structure` | EDAM |  Topic: Quantum chemistry | removed: no topic or synonym containing quantum in the full 3539-class list |
| `simulate.material_behavior` | NAFEMS PSE technical areas |  Materials |  Materials for Analysis and Simulation |
| `simulate.cfd` | NAFEMS PSE technical areas |  Multispecies, Reaction and Combustion |  Multispecies, Reaction & Combustion |
| `simulate.cfd.reacting_flow` | NAFEMS PSE technical areas |  Multispecies, Reaction and Combustion |  Multispecies, Reaction & Combustion |
| `simulate.process_flowsheet` | CAPE-OPEN interface specifications |  CAPE-OPEN Thermodynamic and Physical Properties |  Thermodynamics & Physical Properties |
| `simulate.process_flowsheet.phase_equilibrium` | CAPE-OPEN interface specifications |  CAPE-OPEN Thermodynamic and Physical Properties |  Thermodynamics & Physical Properties |
| `simulate.power_systems` | IEEE PES technical committees |  Power System Planning and Implementation Committee |  Power System Operation, Planning & Economics (PSOPE) |
| `simulate.power_systems.capacity_expansion` | IEEE PES technical committees |  Power System Planning and Implementation Committee |  Power System Operation, Planning & Economics (PSOPE) |
| `simulate.design_exploration` | ASME V&V standards |  V&V 10, V&V 20 and V&V 40 verification, validation and credibility assessment |  V&V 10 (solid mechanics), V&V 20 (CFD and heat transfer), V&V 40 (credibility, medical devices) |
| `simulate.design_exploration.verification_validation` | ASME V&V standards |  V&V 10, V&V 20 and V&V 40 verification, validation and credibility assessment |  V&V 10 (solid mechanics), V&V 20 (CFD and heat transfer), V&V 40 (credibility, medical devices) |

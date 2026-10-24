#create jobs table 
#egypt 
jobs_table <- read.csv("/Users/edmun/Library/CloudStorage/OneDrive-Personal/Edmundo-ITESM/3.Proyectos/51. WB Decarbonization Project/Lybia_CaseStudy/Tableau/employment_results_sector_WB (Sector).csv")
jobs_table$ssp_sector <- do.call(rbind, strsplit(as.character(jobs_table$Strategy), ":"))[,1]
jobs_table$ssp_transformation_name <- do.call(rbind, strsplit(as.character(jobs_table$Strategy), ":"))[,2]
jobs_table <- subset(jobs_table,Country=="EGY")

write.csv(jobs_table,"/Users/edmun/Library/CloudStorage/OneDrive-Personal/Edmundo-ITESM/3.Proyectos/51. WB Decarbonization Project/Egypt_CaseStudy/Tableau/jobs_demand_egypt.csv")

#make adjustments to cba 

cba_data <- read.csv("/Users/edmun/Library/CloudStorage/OneDrive-Personal/Edmundo-ITESM/3.Proyectos/51. WB Decarbonization Project/Lybia_CaseStudy/Tableau/cb_2025-10-31T19;06;18.028884.csv") 
cba_data$valueTest <- ifelse(cba_data$variable=="cb:entc:technical_cost:electricity:capex" & cba_data$time_period<=15,0,cba_data$value)
write.csv(jobs_table,"/Users/edmun/Library/CloudStorage/OneDrive-Personal/Edmundo-ITESM/3.Proyectos/51. WB Decarbonization Project/Lybia_CaseStudy/Tableau/cb_2025-10-31T19;06;18.028884_ct.csv")


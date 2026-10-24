#create job time series 
#create job time series 
root <-  "/Users/edmun/Library/CloudStorage/OneDrive-Personal/Edmundo-ITESM/3.Proyectos/51. WB Decarbonization Project/Egypt_CaseStudy/Tableau/"

#load investment time series
investments <- read.csv(paste0(root,"technical_cost.csv"))  #this comes from tableau 
#job_demand <- read.csv("/Users/edmun/Downloads/direct_jobs_multiplier.csv")
job_demand <- read.csv(paste0(root,"total_jobs_multiplier.csv")) #this comes from tableau 
#we need to merge this by sector 
head(job_demand)
head(investments)

unique(job_demand$Ssp.Sector)
unique(investments$Sector)

#build a crosswalk. 
crosswalk <-  
data.frame (
Ssp.Sector= c("Wastewater treatment","Transportation","Solid Waste","Power Industry","LULUCF","Livestock Manure Management",
"Livestock","Liquid Waste","IPPU","Industrial Energy","Fugitive Emissions","Forest","Crops","CCS","Buildings"),
Sector=c("Waste - Wastewater treatment (trww)","EN - Transportation","Waste - Solid waste","EN - Power Industry (entc)","LULUCF - Forest land","AG - Livestock (manure)",
"AG - Livestock","Waste - Wastewater (liquid waste)","IN - Industrial processes","EN - Industrial combustion","EN - Fugitive emissions","LULUCF - Forest land","AG - Crops","CCS", "EN - Building")
)

#merge demand with crosswalk 
dim(job_demand)
job_demand <- merge(job_demand,crosswalk,by="Ssp.Sector")
dim(job_demand)


#now merge demand with investments

dim(job_demand)
new <- merge(job_demand,investments,by="Sector")
dim(new)

new$Total.Jobs <- new$Total.Jobs*new$Investments*1e3 #total jobs is in jobs per million, investments are in billion 

new$Year <- new$Year1
new$Year1 <- NULL 

d_jobs<-aggregate(list(Total.Jobs=new$Total.Jobs),list(Economic.Sector=new$Economic.Sector,Pathway=new$Pathway,Year=new$Year),sum)

write.csv(d_jobs,paste0(root,"direct_jobs_overtime.csv"),row.names=FALSE)

write.csv(new,paste0(root,"direct_jobs_overtime_ippc_detail.csv"),row.names=FALSE)

unique(new$Ssp.Sector)

#now lets create the baseline labor market 
#for this we need two elements 
#population and labor participation growth
#share of jobs accross the EORA 26 sectors 

#for the next bit, we will only look at the LEP pathway 

d_jobs <- subset(d_jobs,Pathway=="LEP")

#load population projection 
population <- read.csv(paste0(root,"egypt_working_age_2022_2050_wpp2024_anchored_estimate.csv")) 

#we need to merge population with a baseline assumption of labor participation share growth 
labor_force_participation <- data.frame(Year=c(2022:2050), labor_force_participation = approx(c(2022,2050),c(0.45,0.48),xout=c(2022:2050))$y)
#merge 
dim(population)
population <-merge(population,labor_force_participation,by="Year")
dim(population)
#load labor shares 
labor_shares <- read.csv(paste0(root,"Egypt_employment_Fermi_breakdown_by_sector.csv")) 

#labor_shares <- read.csv("/Users/edmun/Downloads/Morocco_employment_Fermi_breakdown_by_sector__adds_to_100__.csv") 
labor_shares$Reference <- NULL
labor_shares$Pct <- labor_shares$Employment.Share..../100
labor_shares$Employment.Share.... <- NULL

#now merge both tables 
labor <- merge(population,labor_shares)
#unemployment_rate <- 0.099
unemployment_rate <- data.frame(Year=c(2022:2050), unemployment_rate = approx(c(2022,2050),c(0.099,0.08),xout=c(2022:2050))$y)
dim(labor)
labor <- merge(labor,unemployment_rate)
dim(labor)

labor$Jobs <- labor$Working_Age_Population_M*labor$labor_force_participation*(1-labor$unemployment_rate)*labor$Pct*1e6
labor <- labor[,c("Economic.Sector","Year","Jobs")]
labor$Pathway <- "Baseline"

#now lets model how the low emissions pathway would chnage this baseline breakdown. 
lowe_pathway <- merge(labor,d_jobs, by=c("Economic.Sector","Year"))
#lowe_pathway$Jobs <- lowe_pathway$Jobs + lowe_pathway$Direct.Jobs
lowe_pathway$Jobs <- lowe_pathway$Jobs + lowe_pathway$Total.Jobs

#now I need to compute how the total change 
new_total <- aggregate(list(Total=lowe_pathway$Jobs),list(Year=lowe_pathway$Year),sum)

#now merge new total 
dim(lowe_pathway)
lowe_pathway <- merge(lowe_pathway,new_total,by="Year")
dim(lowe_pathway)

#estimate percent shares 
lowe_pathway$Share <- lowe_pathway$Jobs/lowe_pathway$Total
#merge with population projection 
dim(lowe_pathway)
lowe_pathway <- merge(lowe_pathway,population)
dim(lowe_pathway)

###
dim(lowe_pathway)
lowe_pathway <- merge(lowe_pathway,unemployment_rate)
dim(lowe_pathway)

###
lowe_pathway$Jobs <- lowe_pathway$Working_Age_Population_M*lowe_pathway$labor_force_participation*(1-lowe_pathway$unemployment_rate)*lowe_pathway$Share*1e6
lowe_pathway <- lowe_pathway[,c("Economic.Sector","Year","Jobs")]
lowe_pathway$Pathway <- "Low Emissions"

#Now what if we assume these jobs are added to the economy 
 dim(labor)
 lowe_Epathway <- merge(labor[,c("Economic.Sector","Year","Jobs")],d_jobs, by=c("Economic.Sector","Year"))
 dim(lowe_Epathway)

 lowe_Epathway$Jobs <- lowe_Epathway$Jobs + lowe_Epathway$Total.Jobs
 lowe_Epathway$Total.Jobs <- NULL
 lowe_Epathway$Pathway <- "Low Emissions-Expansionary"

#rbind both 
laborAll <- rbind(labor,lowe_pathway,lowe_Epathway)

write.csv(laborAll,paste0(root,"total_jobs_overtime.csv"),row.names=FALSE)

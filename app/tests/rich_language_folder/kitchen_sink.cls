/**
 * Heavyweight test file for Tree-Sitter Apex AST indexing.
 * Covers: SOQL/SOSL, DML, Safe Navigation, Trigger Handlers, Inner Classes,
 * Exceptions, Annotations, and Database transactions.
 */
@JsonAccess(serializable='always' deserializable='always')
global with sharing class TreeSitterApexStressTest implements Schedulable, Queueable, Database.Batchable<SObject>, Database.Stateful {
    
    // 1. Static and Instance Variables
    private static final String DEFAULT_STATUS = 'Prospect';
    @TestVisible private Integer executionCount = 0;
    
    // Enums
    public enum PipelineStage { LOGGED, PROCESSING, COMPLETED, FAILED }

    // 2. Inner Wrapper Class & Exception
    public class IndexerWrapper {
        @AuraEnabled public String recordId { get; set; }
        @AuraEnabled public Boolean isProcessed { get; set; }
        
        public IndexerWrapper(String recordId) {
            this.recordId = recordId;
            this.isProcessed = false;
        }
    }
    
    public class CustomIndexerException extends Exception {}

    // 3. AuraEnabled, InvocableMethod, and Complex Collections
    @AuraEnabled(cacheable=true)
    public static List<IndexerWrapper> getActiveRecords(List<Id> accountIds) {
        List<IndexerWrapper> wrappers = new List<IndexerWrapper>();
        
        // Inline SOQL with Bind Variables and Field Aliasing
        for (Account acc : [SELECT Id, Name, (SELECT Id, Email FROM Contacts) 
                            FROM Account 
                            WHERE Id IN :accountIds AND Rating = :DEFAULT_STATUS]) {
            wrappers.add(new IndexerWrapper(acc.Id));
        }
        return wrappers;
    }

    @InvocableMethod(label='Execute Apex Indexer Pipeline' description='Runs AST verification via Flow')
    public static void executeFlowPipeline(List<Id> targetIds) {
        if (!targetIds.isEmpty()) {
            System.enqueueJob(new TreeSitterApexStressTest(targetIds));
        }
    }

    // 4. Constructor & Queueable Interface Implementation
    private List<Id> contextIds;
    public TreeSitterApexStressTest(List<Id> ids) {
        this.contextIds = ids;
    }
    
    public void execute(QueueableContext context) {
        processTransactions(this.contextIds);
    }

    // 5. Schedulable Interface Implementation
    public void execute(SchedulableContext sc) {
        Database.executeBatch(this, 200);
    }

    // 6. Batchable Interface Implementation
    public Database.QueryLocator start(Database.BatchableContext bc) {
        // Dynamic SOQL
        String query = 'SELECT Id, Name, Industry FROM Account WHERE Rating = \'' + String.escapeSingleQuotes(DEFAULT_STATUS) + '\'';
        return Database.getQueryLocator(query);
    }

    public void execute(Database.BatchableContext bc, List<SObject> scope) {
        List<Account> accountsToUpdate = (List<Account>) scope;
        for(Account acc : accountsToUpdate) {
            acc.Description = 'Processed by Tree-sitter Indexer on ' + DateTime.now().format();
        }
        // Database DML with partial success allowed
        Database.SaveResult[] srList = Database.update(accountsToUpdate, false);
    }

    public void finish(Database.BatchableContext bc) {
        System.debug(LoggingLevel.INFO, 'Batch Processing Finished.');
    }

    // 7. Advanced Syntax: SOSL, DML, Safe Navigation (?.)
    public void processTransactions(List<Id> accountIds) {
        // SOSL Search Statement
        List<List<SObject>> searchList = [FIND 'TreeSitter*' IN ALL FIELDS 
                                          RETURNING Account(Id, Name WHERE Id IN :accountIds), 
                                                    Contact(Id, LastName)];
        
        Account[] searchedAccounts = (Account[])searchList[0];
        
        // Safe Navigation Operator (?.) - Coded in Apex since V50.0
        if (searchedAccounts.size() > 0) {
            String accountName = searchedAccounts[0].Name?.toUpperCase();
            System.debug('Processed Top Account Name: ' + accountName);
        }

        // Complex DML Operations with Savepoints
        System.Savepoint sp = Database.setSavepoint();
        try {
            List<Opportunity> newOpps = new List<Opportunity>();
            for(Id accId : accountIds) {
                // SObject instantiation using name-value pairs
                newOpps.add(new Opportunity(
                    Name = 'Indexer Opp ' + accId,
                    StageName = 'Prospecting',
                    CloseDate = Date.today().addDays(30),
                    AccountId = accId
                ));
            }
            
            if(!newOpps.isEmpty()) {
                insert as user newOpps; // User-mode DML (Apex V55.0+)
            }
        } catch(DmlException dmlEx) {
            Database.rollback(sp);
            throw new CustomIndexerException('DML pipeline failed: ' + dmlEx.getDmlMessage(0));
        } catch(Exception ex) {
            Database.rollback(sp);
            throw ex;
        }
    }
}
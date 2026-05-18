/**
 * Heavyweight Apex Trigger AST Stress Test.
 * Target: Tree-sitter Apex / Salesforce Grammar Validation.
 * Covers: Trigger Events, Context Variables, and Router Architectures.
 */
trigger AccountStressTestTrigger on Account (
    before insert, 
    before update, 
    after insert, 
    after update, 
    after delete, 
    after undelete
) {
    // 1. Instantiating a processing pipeline bound to the domain class
    AccountTriggerHandler handler = new AccountTriggerHandler(
        Trigger.new, 
        Trigger.old, 
        Trigger.newMap, 
        Trigger.oldMap
    );

    // 2. Specialized Multi-Branch Context Control Flow Syntax
    if (Trigger.isBefore) {
        if (Trigger.isInsert) {
            handler.handleBeforeInsert();
        } else if (Trigger.isUpdate) {
            handler.handleBeforeUpdate();
        }
    } else if (Trigger.isAfter) {
        switch on Trigger.operationType {
            when AFTER_INSERT {
                handler.handleAfterInsert();
            }
            when AFTER_UPDATE {
                handler.handleAfterUpdate();
            }
            when AFTER_DELETE {
                handler.handleAfterDelete();
            }
            when AFTER_UNDELETE {
                handler.handleAfterUndelete();
            }
            when else {
                System.debug(LoggingLevel.WARN, 'Unrecognized structural execution path matched.');
            }
        }
    }
}